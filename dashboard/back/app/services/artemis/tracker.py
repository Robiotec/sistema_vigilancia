"""
ArtemisTracker — servicio de background que extrae posiciones vehiculares de
theo.24hm.net/Artemis y las empuja al API Central para que aparezcan en el mapa.

Corre como thread daemon dentro del proceso del dashboard. Las credenciales de
sesión (ARTEMIS_SESSION_ID / ARTEMIS_CAPTCHA) se renuevan actualizando el .env
y reiniciando el dashboard, o vía la tabla notification_settings si se prefiere.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
import requests

from back.app.config import Settings, get_settings

logger = logging.getLogger("artemis-tracker")

_LOAD_URL   = "https://theo.24hm.net/Artemis/Pages/Server/LoadInfoAll.aspx"
_UPDATE_URL = "https://theo.24hm.net/Artemis/Pages/Server/UpdateInfoAll.aspx"
_STATE_FILE = Path("/tmp/artemis_tracker_state.json")

_COMPANIES = ("EXPAUSA", "EXPOBONANZA", "GEOMINESUR", "AURIFERA", "COMIMOLL", "COLIBRÍ", "GEODRILL")
_REPORT_TYPES = {
    "REPORTE PERIÓDICO", "REPORTE PERIÓDICO ", "REPORTE PERIODICO",
    "REPORTE DE POSICION", "REPORTE DE POSICION (IGNICION ON)",
    "REPORTE POSICION (IGNICION OFF)", "IGNICION ON", "IGNICION OFF",
    "GPS RESTABLECIDO", "IGNITION OFF SIN MOVIMIENTO",
}

# ─── Helpers de parseo ─────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float | None:
    try:
        return None if v in ("", "---", None) else float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return None if v in ("", "---", None) else int(float(v))
    except (ValueError, TypeError):
        return None


def _normalize_state(s: str) -> str:
    try:
        dt = datetime.strptime(s, "%d/%m/%Y %H:%M:%S")
        return f"{dt.day}/{dt.month}/{dt.year} {dt.strftime('%H:%M:%S')}"
    except ValueError:
        return s


def _parse_gps_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%d/%m/%Y %H:%M:%S")
    except Exception:
        return None


def _parse_vehicle(item: str) -> dict | None:
    parts = item.split("_")
    if len(parts) < 12:
        return None

    is_load = len(parts) > 10 and "*" in parts[9]
    if is_load:
        state_idx, event_idx, addr_idx, geo_idx = 10, 11, 13, 9
    else:
        state_idx, event_idx, addr_idx, geo_idx = 9, 10, 12, None

    v: dict[str, Any] = {
        "imei":             parts[0],
        "plate":            parts[1],
        "lat":              _safe_float(parts[2]),
        "lng":              _safe_float(parts[3]),
        "speed":            _safe_float(parts[4]),
        "heading":          _safe_int(parts[5]),
        "report_id":        parts[6],
        "gps_datetime_raw": parts[7],
        "gps_datetime":     _parse_gps_dt(parts[7]),
        "zone":             parts[8],
        "geofence":         parts[geo_idx] if geo_idx is not None else None,
        "state_number":     parts[state_idx] if len(parts) > state_idx else None,
        "event":            parts[event_idx] if len(parts) > event_idx else None,
        "address":          parts[addr_idx].replace("**", "") if len(parts) > addr_idx else None,
        "status":           None,
        "company":          None,
        "report_type":      None,
    }

    for p in parts:
        clean = p.strip().replace("**", "")
        if clean == "OPERATIVO":
            v["status"] = clean
        elif any(x in clean for x in _COMPANIES):
            v["company"] = clean
        elif clean in _REPORT_TYPES:
            v["report_type"] = clean

    return v


def _parse_response(text: str) -> list[dict]:
    vehicles = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in data:
            if item in ("0_No Updates_REP", "1_Fin Load"):
                continue
            v = _parse_vehicle(item)
            if v:
                vehicles.append(v)
    return vehicles


def _latest_state(vehicles: list[dict], current: str) -> str:
    best_dt: datetime | None = None
    best_raw: str | None = None
    for v in vehicles:
        dt = v.get("gps_datetime")
        raw = v.get("gps_datetime_raw")
        if dt and raw and (best_dt is None or dt > best_dt):
            best_dt, best_raw = dt, raw
    return _normalize_state(best_raw) if best_raw else current

# ─── ArtemisTracker ────────────────────────────────────────────────────────────

class ArtemisTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Config ──────────────────────────────────────────────────────────────────

    def _enabled(self) -> bool:
        return bool(self._s.artemis_session_id and self._s.artemis_captcha)

    def _cookies(self) -> dict:
        return {
            "ASP.NET_SessionId": self._s.artemis_session_id,
            "cplacas": "true",
            "Captcha": self._s.artemis_captcha,
        }

    # ── HTTP ────────────────────────────────────────────────────────────────────

    def _fetch_load(self) -> str:
        r = requests.get(
            _LOAD_URL,
            headers={
                "Accept": "text/event-stream",
                "Referer": "https://theo.24hm.net/Artemis/Pages/Load.js?V=0014",
                "User-Agent": "Mozilla/5.0",
            },
            cookies=self._cookies(),
            params={"state": "0", "p": "1"},
            timeout=30,
        )
        r.raise_for_status()
        return r.text

    def _fetch_updates(self, state: str) -> str:
        r = requests.get(
            _UPDATE_URL,
            headers={
                "Accept": "text/event-stream",
                "Referer": "https://theo.24hm.net/Artemis/Pages/Server.js?V=0014",
                "User-Agent": "Mozilla/5.0",
            },
            cookies=self._cookies(),
            params={"state": state, "ps": "2"},
            timeout=30,
        )
        r.raise_for_status()
        return r.text

    # ── DB ──────────────────────────────────────────────────────────────────────

    def _db_connect(self):
        url = self._s.database_url.replace("postgresql+psycopg://", "postgresql://")
        return psycopg2.connect(url)

    def _load_known_imeis(self) -> set[str]:
        try:
            with self._db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT unique_code FROM vehicles WHERE unique_code IS NOT NULL AND deleted_at IS NULL"
                    )
                    return {row[0] for row in cur.fetchall()}
        except Exception as exc:
            logger.warning("No se pudo cargar IMEIs registrados: %s", exc)
            return set()

    def _ensure_vehicle(self, imei: str, plate: str) -> None:
        try:
            with self._db_connect() as conn:
                with conn.cursor() as cur:
                    # Ya registrado con este IMEI
                    cur.execute(
                        "SELECT id FROM vehicles WHERE unique_code = %s AND deleted_at IS NULL", (imei,)
                    )
                    if cur.fetchone():
                        return
                    # Existe por placa pero sin IMEI — solo actualizar unique_code
                    cur.execute(
                        """SELECT id FROM vehicles
                           WHERE company_id = %s::uuid
                             AND upper(plate) = upper(%s)
                             AND deleted_at IS NULL""",
                        (self._s.artemis_company_id, plate),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            "UPDATE vehicles SET unique_code = %s WHERE id = %s",
                            (imei, row[0]),
                        )
                        conn.commit()
                        logger.info("IMEI asignado a vehículo existente: %s → %s", plate, imei)
                        return
                    cur.execute(
                        """INSERT INTO vehicles (company_id, name, plate, unique_code, vehicle_type, active, can_publish)
                           VALUES (%s::uuid, %s, %s, %s, 'auto', true, false)""",
                        (self._s.artemis_company_id, plate, plate, imei),
                    )
                    conn.commit()
                    logger.info("Vehículo registrado: %s (IMEI %s)", plate, imei)
        except Exception as exc:
            logger.warning("No se pudo registrar vehículo %s: %s", plate, exc)

    # ── Telemetría ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ignition_state(event: str | None) -> str | None:
        if not event:
            return None
        ev = event.upper()
        if "IGNICION ON" in ev or "IGNITION ON" in ev or "ENCENDIDO" in ev:
            return "on"
        if "IGNICION OFF" in ev or "IGNITION OFF" in ev or "SIN MOVIMIENTO" in ev:
            return "off"
        return None

    def _push_telemetry(self, vehicle: dict) -> None:
        if vehicle.get("lat") is None or vehicle.get("lng") is None:
            return
        ignition = self._ignition_state(vehicle.get("event")) or self._ignition_state(vehicle.get("report_type"))
        payload = {
            "lat":          vehicle["lat"],
            "lon":          vehicle["lng"],
            "speed":        vehicle.get("speed"),
            "heading":      vehicle.get("heading"),
            "plate":        vehicle.get("plate"),
            "event":        vehicle.get("event"),
            "ignition":     ignition,
            "status":       vehicle.get("status"),
            "zone":         vehicle.get("zone"),
            "company":      vehicle.get("company"),
            "gps_datetime": vehicle.get("gps_datetime_raw"),
            "address":      vehicle.get("address"),
            "report_type":  vehicle.get("report_type"),
            "source":       "artemis",
        }
        imei = vehicle["imei"]
        try:
            r = requests.post(
                f"{self._s.api_base_url}/telemetry/{imei}",
                json=payload,
                timeout=5,
            )
            if r.status_code != 200:
                logger.warning("Telemetría %s HTTP %s: %s", imei, r.status_code, r.text[:80])
        except Exception as exc:
            logger.warning("Error enviando telemetría %s: %s", imei, exc)

    # ── State ───────────────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            return {}

    def _save_state(self, data: dict) -> None:
        try:
            _STATE_FILE.write_text(json.dumps(data))
        except Exception:
            pass

    # ── Loop ────────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        if not self._enabled():
            logger.info("ArtemisTracker desactivado (sin SESSION_ID/CAPTCHA)")
            return

        today = datetime.now()
        default_state = f"{today.day}/{today.month}/{today.year} 00:00:00"
        last_state_str: str = self._load_state().get("last_state", default_state)
        known_imeis: set[str] = self._load_known_imeis()
        logger.info("ArtemisTracker iniciado | IMEIs en DB: %d | poll: %ds",
                    len(known_imeis), self._s.artemis_poll_interval)

        # vehicle_cache: imei → último dato conocido (para re-emit keepalive)
        vehicle_cache: dict[str, dict] = {}
        # Ciclos sin actualización → cada FULL_RELOAD_CYCLES hacemos carga completa
        FULL_RELOAD_CYCLES = 12  # ~60s con poll de 5s

        def _process_batch(vehicles: list[dict]) -> None:
            for v in vehicles:
                imei = v["imei"]
                if imei not in known_imeis:
                    self._ensure_vehicle(imei, v["plate"])
                    known_imeis.add(imei)
                vehicle_cache[imei] = v
                self._push_telemetry(v)

        # Carga inicial
        try:
            vehicles = _parse_response(self._fetch_load())
            logger.info("Carga inicial Artemis: %d vehículos", len(vehicles))
            _process_batch(vehicles)
            last_state_str = _latest_state(vehicles, last_state_str)
            self._save_state({"last_state": last_state_str})
        except Exception as exc:
            logger.error("Error en carga inicial Artemis: %s", exc)

        # Polling
        cycle = 0
        while not self._stop_event.is_set():
            self._stop_event.wait(self._s.artemis_poll_interval)
            if self._stop_event.is_set():
                break
            cycle += 1
            try:
                if cycle % FULL_RELOAD_CYCLES == 0:
                    # Recarga completa cada ~60s para mantener freshness de vehículos estáticos
                    vehicles = _parse_response(self._fetch_load())
                    logger.debug("Artemis: recarga completa %d vehículos", len(vehicles))
                    _process_batch(vehicles)
                    last_state_str = _latest_state(vehicles, last_state_str)
                    self._save_state({"last_state": last_state_str})
                else:
                    updates = _parse_response(self._fetch_updates(last_state_str))
                    if updates:
                        logger.debug("Artemis: %d actualizaciones", len(updates))
                        _process_batch(updates)
                        last_state_str = _latest_state(updates, last_state_str)
                        self._save_state({"last_state": last_state_str})
                    elif vehicle_cache:
                        # Re-emitir caché para que el dashboard no marque como lost
                        for v in vehicle_cache.values():
                            self._push_telemetry(v)
            except requests.exceptions.RequestException as exc:
                logger.warning("Artemis: error de conexión: %s", exc)
            except Exception as exc:
                logger.error("Artemis: error inesperado: %s", exc, exc_info=True)

        logger.info("ArtemisTracker detenido")

    # ── API pública ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="artemis-tracker")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
