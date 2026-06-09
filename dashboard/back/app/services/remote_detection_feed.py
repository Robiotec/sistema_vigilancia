from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import json
import mimetypes
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse, urlunparse

import urllib.request
import psycopg2
from psycopg2.extras import Json, RealDictCursor

from back.app.config import Settings

ECUADOR_TZ = timezone(timedelta(hours=-5))
VIDEO_EVENT_TYPES = {"clip", "click", "clips_movimiento", "clips_zona"}


@dataclass(slots=True)
class RemoteCameraEvent:
    event_type: str
    cam_id: str
    timestamp: int
    source_file: str
    crop_path: str
    video_path: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.payload)
        if self.event_type in VIDEO_EVENT_TYPES:
            return {
                "event_type": self.event_type,
                "cam_id": self.cam_id,
                "timestamp": self.timestamp,
                "source_file": self.source_file,
                "crop_path": self.crop_path,
                "video_path": self.video_path,
                "track_id": str(payload.get("track_id") or "").strip(),
                "display_title": self._video_display_title(self.event_type),
                "rows": self._clip_rows(payload),
            }

        if self.event_type == "person":
            raw_name = str(payload.get("person_name") or "").strip()
            parts = raw_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            extra_info = payload.get("person_info") if isinstance(payload.get("person_info"), dict) else {}
            confidence_raw = payload.get("confidence")
            try:
                confidence_pct = f"{float(confidence_raw) * 100:.1f}%"
            except (TypeError, ValueError):
                confidence_pct = None
            rows: list[dict[str, str]] = [
                {"label": "nombre", "value": extra_info.get("nombre") or first_name or raw_name or "Sin dato"},
                {"label": "apellido", "value": extra_info.get("apellido") or last_name or "Sin dato"},
                {"label": "cédula", "value": str(payload.get("person_id") or extra_info.get("cedula") or "Sin dato")},
            ]
            if confidence_pct:
                print("Confidence:", confidence_pct)
                rows.append({"label": "confianza", "value": confidence_pct})
            for k, v in extra_info.items():
                if k.lower() not in {"nombre", "apellido", "cedula"}:
                    rows.append({"label": k, "value": str(v) if v is not None else "Sin dato"})
            return {
                "event_type": self.event_type,
                "cam_id": self.cam_id,
                "timestamp": self.timestamp,
                "source_file": self.source_file,
                "crop_path": self.crop_path,
                "video_path": self.video_path,
                "person_id": str(payload.get("person_id") or "").strip(),
                "person_name": raw_name,
                "display_title": "Persona detectada",
                "rows": rows,
            }

        vehicle_info = payload.get("vehicle_info") if isinstance(payload.get("vehicle_info"), dict) else {}
        _v = vehicle_info
        plate_rows: list[dict[str, str]] = [
            {"label": "placa",                   "value": str(payload.get("plate") or _v.get("Placa") or "Sin dato")},
            {"label": "marca",                   "value": str(_v.get("Marca") or "Sin dato")},
            {"label": "modelo",                  "value": str(_v.get("Modelo") or "Sin dato")},
            {"label": "color",                   "value": str(_v.get("Color") or "Sin dato")},
            {"label": "año",                     "value": str(_v.get("Año Vehículo") or "Sin dato")},
            {"label": "tipo servicio",           "value": str(_v.get("Tipo Servicio") or "Sin dato")},
            {"label": "capacidad",               "value": str(_v.get("Capacidad") or "Sin dato")},
            {"label": "cilindraje",              "value": str(_v.get("Cilindraje") or "Sin dato")},
            {"label": "tonelaje",                "value": str(_v.get("Tonelaje") or "Sin dato")},
            {"label": "caducidad matrícula",     "value": str(_v.get("Caducidad Matrícula") or "Sin dato")},
            {"label": "último trámite",          "value": str(_v.get("Último Trámite") or "Sin dato")},
            {"label": "GAD trámite",             "value": str(_v.get("GAD Último Trámite") or "Sin dato")},
            {"label": "traspasos",               "value": str(_v.get("Numero de Traspasos") or "Sin dato")},
            {"label": "reportado robado",        "value": str(_v.get("Reportado Robado") or "Sin dato")},
            {"label": "prenda comercial",        "value": str(_v.get("Prenda Comercial") or "Sin dato")},
            {"label": "prenda industrial",       "value": str(_v.get("Prenda Industrial") or "Sin dato")},
            {"label": "prohibición enajenar",    "value": str(_v.get("Prohibición Enajenar") or "Sin dato")},
            {"label": "remarcado motor",         "value": str(_v.get("Remarcado Motor") or "Sin dato")},
            {"label": "remarcado chasis",        "value": str(_v.get("Remarcado Chasis") or "Sin dato")},
            {"label": "reserva dominio",         "value": str(_v.get("Reserva Dominio") or "Sin dato")},
            {"label": "pagado SRI",              "value": str(_v.get("PAGADO SRI") or "Sin dato")},
            {"label": "multas pendientes",       "value": str(_v.get("Multas Pendientes De Pago") or "Sin dato")},
            {"label": "rodaje provincial 2026",  "value": str(_v.get("Pago Rodaje Provincial 2026") or "Sin dato")},
            {"label": "revisión vigente 2026",   "value": str(_v.get("Revisión Vigente 2026") or "Sin dato")},
            {"label": "condición",               "value": str(_v.get("Condición") or "Sin dato")},
            {"label": "fecha",                   "value": str(_v.get("Fecha") or "Sin dato")},
        ]
        return {
            "event_type": self.event_type,
            "cam_id": self.cam_id,
            "timestamp": self.timestamp,
            "source_file": self.source_file,
            "crop_path": self.crop_path,
            "video_path": self.video_path,
            "plate": str(payload.get("plate") or "").strip(),
            "display_title": "Vehículo detectado",
            "rows": plate_rows,
        }

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        try:
            timestamp = int(float(value))
        except (TypeError, ValueError):
            return str(value or "Sin dato")
        if timestamp <= 0:
            return "Sin dato"
        return datetime.fromtimestamp(timestamp, tz=ECUADOR_TZ).strftime("%d/%m/%Y, %I:%M:%S %p")

    @classmethod
    def _clip_rows(cls, payload: dict[str, Any]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if "timestamp" in payload:
            rows.append({"label": "timestamp", "value": cls._format_timestamp(payload.get("timestamp"))})
        if "duration" in payload:
            rows.append({"label": "duration", "value": f"{payload.get('duration')} s"})
        return rows or [{"label": "datos", "value": "Sin dato"}]

    @staticmethod
    def _video_display_title(event_type: str) -> str:
        return {
            "clip": "Video de zona detectado",
            "clips_movimiento": "Movimiento detectado",
            "clips_zona": "Alerta de zona detectada",
        }.get(event_type, "Video detectado")


class RemoteDetectionFeedService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.video_cache_dir = Path(__file__).resolve().parents[1] / "data" / "event_videos"
        self._video_warm_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-video-cache")
        self._video_warm_lock = threading.Lock()
        self._video_warming: set[str] = set()
        self._video_cache_locks: dict[str, threading.Lock] = {}
        self._video_cache_locks_lock = threading.Lock()
        self._camera_name_cache: dict[str, str | None] = {}

    def fetch_camera_events(self, cam_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
        normalized_cam_id = str(cam_id or "").strip()
        if not normalized_cam_id:
            return []

        sql = """
            SELECT
                event_type, camera_id, event_timestamp,
                json_file_path, crop_path, video_file_path, detail_payload
            FROM camera_event_history
            WHERE camera_id = %s
            ORDER BY detected_at DESC, created_at DESC
            LIMIT %s
        """
        with self._db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (normalized_cam_id, max(1, min(int(limit), 24))))
                rows = cur.fetchall()

        events = [
            RemoteCameraEvent(
                event_type=str(row.get("event_type") or "").strip(),
                cam_id=str(row.get("camera_id") or "").strip(),
                timestamp=int(row.get("event_timestamp") or 0),
                source_file=str(row.get("json_file_path") or "").strip(),
                crop_path=str(row.get("crop_path") or "").strip(),
                video_path=str(row.get("video_file_path") or "").strip(),
                payload=row.get("detail_payload") if isinstance(row.get("detail_payload"), dict) else {},
            )
            for row in rows
        ]
        rendered_events = [event.to_dict() for event in events]
        try:
            self._enrich_plate_events_from_db(rendered_events)
        except Exception:
            pass
        self._warm_recent_videos(rendered_events)
        return rendered_events

    def _enrich_plate_events_from_db(self, events: list[dict[str, Any]]) -> None:
        """Lee el vehicle_info ya enriquecido por plate_lookup_sync_worker desde la DB.

        No llama a 10.0.0.3 directamente — eso es responsabilidad exclusiva del worker.
        """
        plates = list({
            str(e.get("plate") or "").strip()
            for e in events
            if str(e.get("event_type") or "") == "plate" and str(e.get("plate") or "").strip()
        })
        if not plates:
            return
        with self._db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (plate)
                        plate,
                        detail_payload
                    FROM camera_event_history
                    WHERE event_type = 'plate'
                      AND plate = ANY(%s)
                    ORDER BY plate, detected_at DESC
                    """,
                    (plates,),
                )
                rows = cur.fetchall()

        by_plate: dict[str, dict[str, Any]] = {}
        for row in rows:
            plate = str(row.get("plate") or "").strip()
            dp = row.get("detail_payload") if isinstance(row.get("detail_payload"), dict) else {}
            if plate:
                by_plate[plate] = dp

        for event in events:
            if str(event.get("event_type") or "") != "plate":
                continue
            plate = str(event.get("plate") or "").strip()
            if not plate or plate not in by_plate:
                continue
            dp = by_plate[plate]
            record = dp.get("vehicle_info_record") if isinstance(dp.get("vehicle_info_record"), dict) else {}
            if not record:
                continue
            enriched_rows = self._plate_lookup_rows(record)
            if enriched_rows:
                event["rows"] = enriched_rows
            event["plate_lookup"] = {
                "status": record.get("status"),
                "ready": bool(record.get("ready")),
                "pending": bool(record.get("pending")),
                "updated_at": dp.get("vehicle_info_checked_at"),
                "source_errors": record.get("source_errors") if isinstance(record.get("source_errors"), dict) else {},
            }

    @staticmethod
    def _plate_lookup_rows(lookup: dict[str, Any]) -> list[dict[str, str]]:
        def value(*keys: str) -> str:
            for key in keys:
                raw = lookup.get(key)
                if raw not in (None, ""):
                    return str(raw)
            return "Sin dato"

        rows = [
            {"label": "placa", "value": value("placa")},
            {"label": "estado consulta", "value": value("status")},
            {"label": "propietario", "value": value("propietario")},
            {"label": "marca", "value": value("marca")},
            {"label": "modelo", "value": value("modelo")},
            {"label": "año", "value": value("anio")},
            {"label": "país fabricación", "value": value("pais_fabricacion")},
            {"label": "clase", "value": value("clase")},
            {"label": "tipo", "value": value("tipo")},
            {"label": "servicio", "value": value("servicio")},
            {"label": "uso", "value": value("uso")},
            {"label": "color", "value": " / ".join(v for v in [value("color_1"), value("color_2")] if v != "Sin dato") or "Sin dato"},
            {"label": "vin", "value": value("vin")},
            {"label": "motor", "value": value("motor")},
            {"label": "cantón matrícula", "value": value("canton_matricula")},
            {"label": "fecha matrícula", "value": value("fecha_matricula")},
            {"label": "vence matrícula", "value": value("vencimiento_matricula")},
            {"label": "fecha inspección", "value": value("fecha_inspeccion")},
            {"label": "último pago", "value": value("ultimo_pago")},
            {"label": "cilindraje", "value": value("cilindraje")},
            {"label": "estado", "value": value("estado")},
            {"label": "información", "value": value("informacion")},
        ]
        return rows

    def fetch_event_history(
        self,
        *,
        page: int = 1,
        page_size: int = 8,
        query: str = "",
        date_from: str = "",
        date_to: str = "",
        time_from: str = "",
        time_to: str = "",
        camera_id: str = "",
        camera_name: str = "",
        categories: str = "",
        event_types: str = "",
        origins: str = "",
        statuses: str = "",
    ) -> dict[str, Any]:
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 8), 50))
        where_sql, params = self._history_filters(
            query=query,
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            camera_id=camera_id,
            camera_name=camera_name,
            categories=categories,
            event_types=event_types,
            origins=origins,
            statuses=statuses,
        )
        offset = (page - 1) * page_size

        count_sql = f"SELECT count(*) AS total FROM camera_event_history {where_sql}"
        list_sql = f"""
            SELECT
                id,
                event_type,
                event_category,
                origin,
                camera_id,
                camera_name,
                camera_location,
                event_timestamp,
                detected_at,
                detected_date,
                title,
                description,
                person_id,
                person_name,
                plate,
                track_id,
                status,
                severity,
                json_file_path,
                video_file_path,
                image_file_path,
                crop_path,
                detail_payload
            FROM camera_event_history
            {where_sql}
            ORDER BY detected_at DESC, created_at DESC
            LIMIT %s OFFSET %s
        """

        with self._db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(count_sql, params)
                total = int((cur.fetchone() or {}).get("total") or 0)
                cur.execute(list_sql, [*params, page_size, offset])
                rows = [self._history_item(row) for row in cur.fetchall()]

        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def update_event_history_status(self, event_id: str, status: str) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"new", "reviewed", "archived", "dismissed"}:
            raise ValueError("Estado no permitido")
        with self._db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE camera_event_history
                    SET status = %s, updated_at = now()
                    WHERE id = %s
                    RETURNING id, status
                    """,
                    (normalized_status, event_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise FileNotFoundError("Evento no encontrado")
        return {"id": str(row["id"]), "status": row["status"]}

    def fetch_event_history_filter_options(self, field: str) -> dict[str, Any]:
        normalized_field = str(field or "").strip().lower()
        if normalized_field == "camera_id":
            query = """
                SELECT
                    camera_id AS value,
                    camera_id AS label,
                    count(*) AS total
                FROM camera_event_history
                WHERE camera_id IS NOT NULL AND camera_id <> ''
                GROUP BY camera_id
                ORDER BY camera_id
            """
        elif normalized_field == "camera_name":
            query = """
                SELECT
                    camera_name AS value,
                    camera_name AS label,
                    count(*) AS total
                FROM camera_event_history
                WHERE camera_name IS NOT NULL AND camera_name <> ''
                GROUP BY camera_name
                ORDER BY camera_name
            """
        else:
            raise ValueError("Filtro no permitido")

        with self._db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                rows = cur.fetchall()

        items = [
            {
                "value": str(row.get("value") or ""),
                "label": str(row.get("label") or ""),
                "count": int(row.get("total") or 0),
            }
            for row in rows
            if str(row.get("value") or "").strip()
        ]
        return {"items": items, "total": len(items)}

    def read_remote_file(self, remote_path: str) -> tuple[bytes, str]:
        url = str(remote_path or "").strip()
        if not url:
            raise FileNotFoundError("Ruta vacía")
        if not url.startswith(("http://", "https://")):
            raise FileNotFoundError(f"Ruta no es URL MinIO: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "RobiotecDashboard/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
        except Exception as exc:
            raise FileNotFoundError(f"No se pudo descargar {url}: {exc}") from exc
        media_type, _ = mimetypes.guess_type(url)
        return content, media_type or "application/octet-stream"

    def cache_remote_video(self, remote_path: str) -> tuple[Path, str]:
        url = str(remote_path or "").strip()
        if not url:
            raise FileNotFoundError("Ruta vacía")
        if not url.startswith(("http://", "https://")):
            raise FileNotFoundError(f"Ruta no es URL MinIO: {url}")
        with self._cache_lock(url):
            return self._cache_remote_video_locked(url)

    def _cache_remote_video_locked(self, url: str) -> tuple[Path, str]:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        suffix = PurePosixPath(parsed.path).suffix or ".mp4"
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        source_path = self.video_cache_dir / f"{cache_key}{suffix}"
        browser_path = self.video_cache_dir / f"{cache_key}.browser.mp4"
        browser_ok_path = self.video_cache_dir / f"{cache_key}.browser-ok"
        partial_path = source_path.with_suffix(f"{source_path.suffix}.part")

        self.video_cache_dir.mkdir(parents=True, exist_ok=True)
        if browser_path.exists() and browser_path.stat().st_size > 0:
            return browser_path, "video/mp4"

        if not source_path.exists() or source_path.stat().st_size == 0:
            req = urllib.request.Request(url, headers={"User-Agent": "RobiotecDashboard/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with partial_path.open("wb") as fh:
                        while True:
                            chunk = resp.read(1024 * 1024)
                            if not chunk:
                                break
                            fh.write(chunk)
            except Exception as exc:
                raise FileNotFoundError(f"No se pudo descargar {url}: {exc}") from exc
            partial_path.replace(source_path)

        if browser_ok_path.exists():
            return source_path, "video/mp4"
        if self._is_browser_video(source_path):
            browser_ok_path.touch(exist_ok=True)
            return source_path, "video/mp4"

        self._ensure_browser_video(source_path, browser_path)
        return browser_path, "video/mp4"

    def _resolve_sftp_file(self, sftp: Any, remote_path: str) -> str:  # noqa: unused — kept for compat
        candidates: list[str] = [remote_path]
        for candidate in candidates:
            try:
                sftp.stat(candidate)
                return candidate
            except Exception:
                continue
            except OSError:
                continue
        raise FileNotFoundError(remote_path)

    def _cache_lock(self, normalized_path: str) -> threading.Lock:
        with self._video_cache_locks_lock:
            lock = self._video_cache_locks.get(normalized_path)
            if lock is None:
                lock = threading.Lock()
                self._video_cache_locks[normalized_path] = lock
            return lock

    def _warm_recent_videos(self, events: list[dict[str, Any]], limit: int = 3) -> None:
        video_paths: list[str] = []
        for event in events:
            path = str(event.get("video_path") or "").strip()
            if path:
                video_paths.append(path)
            if len(video_paths) >= limit:
                break

        for path in video_paths:
            self._warm_video_async(path)

    def _warm_video_async(self, remote_path: str) -> None:
        with self._video_warm_lock:
            if remote_path in self._video_warming:
                return
            self._video_warming.add(remote_path)
        self._video_warm_executor.submit(self._warm_video, remote_path)

    def _warm_video(self, remote_path: str) -> None:
        try:
            self.cache_remote_video(remote_path)
        except Exception:
            pass
        finally:
            with self._video_warm_lock:
                self._video_warming.discard(remote_path)

    def _db_connection(self):
        return psycopg2.connect(self._psycopg_dsn(self.settings.database_url))

    @classmethod
    def _history_filters(cls, **filters: str) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        query = str(filters.get("query") or "").strip()
        if query:
            pattern = f"%{query}%"
            clauses.append(
                """(
                    camera_id ILIKE %s OR
                    camera_name ILIKE %s OR
                    title ILIKE %s OR
                    description ILIKE %s OR
                    person_name ILIKE %s OR
                    person_id ILIKE %s OR
                    plate ILIKE %s OR
                    detail_payload::text ILIKE %s
                )"""
            )
            params.extend([pattern] * 8)

        for field, column in (("date_from", "detected_date"), ("date_to", "detected_date")):
            value = str(filters.get(field) or "").strip()
            if not value:
                continue
            operator = ">=" if field.endswith("from") else "<="
            clauses.append(f"{column} {operator} %s::date")
            params.append(value)

        time_from = str(filters.get("time_from") or "").strip()
        if time_from:
            clauses.append("(detected_at AT TIME ZONE 'America/Guayaquil')::time >= %s::time")
            params.append(time_from)

        time_to = str(filters.get("time_to") or "").strip()
        if time_to:
            clauses.append("(detected_at AT TIME ZONE 'America/Guayaquil')::time <= %s::time")
            params.append(time_to)

        camera_id = str(filters.get("camera_id") or "").strip()
        if camera_id:
            clauses.append("camera_id = %s")
            params.append(camera_id)

        camera_name = str(filters.get("camera_name") or "").strip()
        if camera_name:
            clauses.append("camera_name = %s")
            params.append(camera_name)

        for field, column, allowed in (
            ("categories", "event_category", {"alerta", "acceso", "reconocimiento_facial", "movimiento", "vehiculo", "sistema"}),
            ("event_types", "event_type", {"person", "plate", "clip", "click", "clips_movimiento", "clips_zona"}),
            ("origins", "origin", {"fixed_camera", "vehicle", "drone", "system"}),
            ("statuses", "status", {"new", "reviewed", "archived", "dismissed"}),
        ):
            raw_value = filters.get(field)
            values = cls._csv_values(raw_value, allowed)
            if values:
                placeholders = ", ".join(["%s"] * len(values))
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)
            elif str(raw_value or "").strip():
                clauses.append("false")

        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _csv_values(raw: Any, allowed: set[str]) -> list[str]:
        values = []
        for value in str(raw or "").split(","):
            normalized = value.strip().lower()
            if normalized in allowed and normalized not in values:
                values.append(normalized)
        return values

    @staticmethod
    def _history_item(row: dict[str, Any]) -> dict[str, Any]:
        detected_at = row.get("detected_at")
        detected_date = row.get("detected_date")
        payload = row.get("detail_payload") if isinstance(row.get("detail_payload"), dict) else {}
        return {
            "id": str(row.get("id") or ""),
            "event_type": row.get("event_type"),
            "event_category": row.get("event_category"),
            "origin": row.get("origin"),
            "camera_id": row.get("camera_id"),
            "camera_name": row.get("camera_name"),
            "camera_location": row.get("camera_location"),
            "event_timestamp": row.get("event_timestamp"),
            "detected_at": detected_at.isoformat() if hasattr(detected_at, "isoformat") else detected_at,
            "detected_date": detected_date.isoformat() if hasattr(detected_date, "isoformat") else detected_date,
            "title": row.get("title"),
            "description": row.get("description"),
            "person_id": row.get("person_id"),
            "person_name": row.get("person_name"),
            "plate": row.get("plate"),
            "track_id": row.get("track_id"),
            "status": row.get("status"),
            "severity": row.get("severity"),
            "json_file_path": row.get("json_file_path"),
            "video_file_path": row.get("video_file_path"),
            "image_file_path": row.get("image_file_path"),
            "crop_path": row.get("crop_path"),
            "detail_payload": payload,
        }

    @staticmethod
    def _psycopg_dsn(database_url: str) -> str:
        if database_url.startswith("postgresql+psycopg://"):
            parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
            return urlunparse(parsed)
        return database_url

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _event_category(event_type: str) -> str:
        return {
            "person": "reconocimiento_facial",
            "plate": "vehiculo",
            "clip": "movimiento",
            "click": "movimiento",
            "clips_movimiento": "movimiento",
            "clips_zona": "alerta",
        }.get(event_type, event_type)

    @staticmethod
    def _event_title(event_type: str) -> str:
        return {
            "person": "Persona detectada",
            "plate": "Vehiculo detectado",
            "clip": "Video de zona detectado",
            "click": "Video detectado",
            "clips_movimiento": "Movimiento detectado",
            "clips_zona": "Alerta de zona detectada",
        }.get(event_type, "Evento detectado")

    @staticmethod
    def _event_description(event_type: str, payload: dict[str, Any]) -> str | None:
        if event_type in VIDEO_EVENT_TYPES and payload.get("duration") is not None:
            return f"Clip de video generado con duracion {payload.get('duration')} s."
        return None

    @staticmethod
    def _event_severity(event_type: str) -> str:
        return "info" if event_type in {"person", "plate", *VIDEO_EVENT_TYPES} else "warning"

    def _camera_name(self, camera_id: str) -> str | None:
        if camera_id in self._camera_name_cache:
            return self._camera_name_cache[camera_id]

        query = "SELECT name FROM cameras WHERE unique_code = %s LIMIT 1"
        try:
            with self._db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (camera_id,))
                    row = cur.fetchone()
                    name = str(row[0]).strip() if row and row[0] else None
                    self._camera_name_cache[camera_id] = name
                    return name
        except Exception:
            self._camera_name_cache[camera_id] = None
            return None

    @staticmethod
    def _is_browser_video(source_path: Path) -> bool:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        if completed.returncode != 0:
            return False
        return completed.stdout.strip().lower() in {"h264", "avc1"}

    @staticmethod
    def _ensure_browser_video(source_path: Path, browser_path: Path) -> None:
        if browser_path.exists() and browser_path.stat().st_size > 0:
            return

        partial_path = browser_path.with_suffix(f"{browser_path.suffix}.part")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(partial_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "No se pudo convertir el video a H.264")
        partial_path.replace(browser_path)

