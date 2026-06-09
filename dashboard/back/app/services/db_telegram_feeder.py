"""Feeder de Telegram basado en DB: lee camera_event_history y alimenta el outbox."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from back.app.config import Settings
from back.app.services.send_telegram import (
    send_configured_telegram_photo,
    send_configured_telegram_text,
    send_configured_telegram_video,
)
from back.app.services.telegram_alert_worker import TelegramAlertWorker

_log = logging.getLogger(__name__)

ECUADOR_TZ = timezone(timedelta(hours=-5))
_FFMPEG_LOCK = threading.Lock()

TELEGRAM_EVENT_LABELS = {
    "clip": "Video detectado",
    "clips_zona": "Alerta de zona",
    "clips_movimiento": "Movimiento detectado",
    "click": "Evento de click",
    "plate": "Placa detectada",
    "person": "Persona identificada",
}

# Cooldown por (camera_id, key) para evitar spam de la misma placa/persona
_COOLDOWN_SECS = 300  # 5 minutos
_cooldown_cache: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def _check_cooldown(key: str) -> bool:
    """Retorna True si el evento debe enviarse (no está en cooldown)."""
    now = time.time()
    with _cooldown_lock:
        last = _cooldown_cache.get(key, 0.0)
        if now - last < _COOLDOWN_SECS:
            return False
        _cooldown_cache[key] = now
        return True


class DBTelegramFeeder:
    """Polling de camera_event_history → inserta en camera_alert_outbox → envía Telegram."""

    def __init__(self, settings: Settings, *, poll_interval: float = 5.0) -> None:
        self.settings = settings
        self.poll_interval = max(2.0, float(poll_interval))
        self._db_dsn = self._psycopg_dsn(settings.database_url)

        self._crop_cache_dir = Path(__file__).resolve().parents[1] / "data" / "telegram_clip_crops"
        self._crop_cache_dir.mkdir(parents=True, exist_ok=True)

        self._worker = TelegramAlertWorker(
            db_dsn=self._db_dsn,
            send_video_fn=lambda msg, path: send_configured_telegram_video(message=msg, video_path=path),
            send_photo_fn=lambda msg, path: send_configured_telegram_photo(message=msg, image_path=path),
            send_text_fn=lambda msg: send_configured_telegram_text(message=msg),
            cache_remote_file_fn=self._download_url,
            render_video_fn=self._render_video,
        )
        self._worker.ensure_schema()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "running": False, "last_error": "", "last_checked_at": "",
            "last_sent_total": 0, "outbox_pending": 0,
        }

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="db-telegram-feeder", daemon=True)
        self._thread.start()
        self._set_status(running=True)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._set_status(running=False)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def check_once(self) -> dict[str, Any]:
        self._set_status(last_checked_at=datetime.now(ECUADOR_TZ).isoformat(), last_error="")
        enqueued = 0
        try:
            enqueued = self._feed_new_events()
        except Exception as exc:
            _log.error("[feeder] error en feed: %s", exc)
            self._set_status(last_error=str(exc))
        # drain() siempre corre, independientemente de si feed falló
        sent = self._worker.drain()
        if sent:
            self._set_status(last_sent_total=sent)
        self._set_status(outbox_pending=self._worker.pending_count())
        return {"enqueued": enqueued, "sent": sent}

    # ── loop ──────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception as exc:
                self._set_status(last_error=str(exc), last_checked_at=datetime.now(ECUADOR_TZ).isoformat())
            finally:
                self._stop_event.wait(self.poll_interval)
        self._set_status(running=False)

    # ── feed logic ────────────────────────────────────────────────────────────

    def _feed_new_events(self) -> int:
        watermark = self._load_watermark()
        sql = """
            SELECT id, event_type, camera_id, camera_name, event_timestamp,
                   video_file_path, crop_path, detail_payload,
                   plate, person_name, person_id, created_at
            FROM camera_event_history
            WHERE created_at > %s
              AND (video_file_path LIKE 'http%%' OR crop_path LIKE 'http%%')
            ORDER BY created_at ASC, id ASC
            LIMIT 50
        """
        with psycopg2.connect(self._db_dsn) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (watermark,))
                rows = cur.fetchall()

        if not rows:
            return 0

        cam_ids = {str(r["camera_id"]) for r in rows if r.get("camera_id")}
        notif_flags = self._camera_notif_flags(cam_ids)

        enqueued = 0
        for row in rows:
            cam_id = str(row.get("camera_id") or "")
            flags = notif_flags.get(cam_id, {"telegram": True, "email": True})
            uid = self._make_uid(row)

            if flags.get("telegram", True):
                # Cooldown para placas y personas para evitar spam
                event_type = str(row.get("event_type") or "")
                if not self._passes_cooldown(event_type, cam_id, row):
                    continue
                payload = self._build_payload(row)
                if self._worker.insert_pending(uid, cam_id, event_type, payload):
                    enqueued += 1

            if flags.get("email", True):
                threading.Thread(
                    target=self._send_event_email,
                    args=(row,),
                    daemon=True,
                    name="event-email",
                ).start()

        self._save_watermark(rows[-1]["created_at"])
        return enqueued

    def _passes_cooldown(self, event_type: str, cam_id: str, row: dict[str, Any]) -> bool:
        if event_type == "plate":
            plate_num = str(row.get("plate") or (row.get("detail_payload") or {}).get("plate") or "")
            if plate_num:
                return _check_cooldown(f"plate:{cam_id}:{plate_num}")
        elif event_type == "person":
            person_id = str(row.get("person_id") or (row.get("detail_payload") or {}).get("person_id") or "")
            if person_id:
                return _check_cooldown(f"person:{cam_id}:{person_id}")
        return True

    def _camera_notif_flags(self, cam_ids: set[str]) -> dict[str, dict[str, bool]]:
        if not cam_ids:
            return {}
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT unique_code,
                               COALESCE(notification_telegram, true) AS notif_tg,
                               COALESCE(notification_email, true)    AS notif_em
                        FROM cameras
                        WHERE unique_code = ANY(%s)
                          AND deleted_at IS NULL
                        """,
                        (list(cam_ids),),
                    )
                    return {
                        str(r[0]): {"telegram": bool(r[1]), "email": bool(r[2])}
                        for r in cur.fetchall()
                    }
        except Exception as exc:
            _log.warning("[feeder] no se pudo leer flags de notificacion: %s", exc)
            return {}

    def _send_event_email(self, row: dict[str, Any]) -> None:
        try:
            from back.app.services.notification_settings import (
                load_email_recipients_from_db,
                load_notification_settings,
            )
            from back.app.services.send_mail import send_email

            recipients = load_email_recipients_from_db() or []
            if not recipients:
                return

            cfg = load_notification_settings().get("email", {})
            if not cfg.get("sender_email") or not cfg.get("sender_password"):
                return

            ts = int(row.get("event_timestamp") or 0)
            detected = (
                datetime.fromtimestamp(ts, tz=ECUADOR_TZ).strftime("%d/%m/%Y %H:%M:%S")
                if ts else "Sin dato"
            )
            label = TELEGRAM_EVENT_LABELS.get(str(row.get("event_type") or ""), "Evento detectado")
            cam_id = str(row.get("camera_id") or "Sin dato")
            video_url = str(row.get("video_file_path") or row.get("crop_path") or "")

            body_lines = [
                "ALERTA DE EVENTO",
                "",
                f"Tipo: {label}",
                f"Cámara: {cam_id}",
                f"Hora: {detected}",
            ]
            if video_url.startswith("http"):
                body_lines.append(f"Archivo: {video_url}")

            send_email({
                "sender_email": cfg.get("sender_email", ""),
                "sender_password": cfg.get("sender_password", ""),
                "smtp_host": cfg.get("smtp_host", "smtp.gmail.com"),
                "smtp_port": int(cfg.get("smtp_port") or 587),
                "recipients": recipients,
                "subject": f"[Robiotec] {label} — {cam_id}",
                "message": "\n".join(body_lines),
            })
            _log.info("[feeder] Email enviado para cam=%s tipo=%s", cam_id, row.get("event_type"))
        except Exception as exc:
            _log.warning("[feeder] Error enviando email: %s", exc)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        ts = int(row.get("event_timestamp") or 0)
        detected = datetime.fromtimestamp(ts, tz=ECUADOR_TZ).strftime("%d/%m/%Y %H:%M:%S") if ts else "Sin dato"
        event_type = str(row.get("event_type") or "")
        cam_id = str(row.get("camera_id") or "Sin dato")
        cam_name = str(row.get("camera_name") or cam_id)
        detail = row.get("detail_payload") or {}

        if event_type == "plate":
            plate_num = str(row.get("plate") or detail.get("plate") or "Sin dato")
            vehicle_info = detail.get("vehicle_info") or {}
            lines = [
                "🚗 PLACA DETECTADA",
                "",
                f"Placa: {plate_num}",
            ]
            if vehicle_info:
                marca = vehicle_info.get("marca") or vehicle_info.get("brand") or ""
                modelo = vehicle_info.get("modelo") or vehicle_info.get("model") or ""
                color = vehicle_info.get("color") or ""
                if marca or modelo:
                    lines.append(f"Vehículo: {marca} {modelo}".strip())
                if color:
                    lines.append(f"Color: {color}")
            lines += [f"Cámara: {cam_name}", f"Hora: {detected}"]
            msg = "\n".join(lines)
        elif event_type == "person":
            name = str(row.get("person_name") or detail.get("person_name") or "Desconocido")
            person_id = str(row.get("person_id") or detail.get("person_id") or "")
            conf = float(detail.get("confidence") or 0)
            lines = [
                "👤 PERSONA IDENTIFICADA",
                "",
                f"Nombre: {name}",
            ]
            if person_id:
                lines.append(f"Cédula: {person_id}")
            lines += [
                f"Confianza: {conf:.0%}",
                f"Cámara: {cam_name}",
                f"Hora: {detected}",
            ]
            msg = "\n".join(lines)
        else:
            label = TELEGRAM_EVENT_LABELS.get(event_type, "Evento detectado")
            msg = "\n".join([
                f"⚠️ {label.upper()}",
                "",
                f"Cámara: {cam_name}",
                f"Hora: {detected}",
            ])

        video = str(row.get("video_file_path") or "")
        crop = str(row.get("crop_path") or "")
        return {
            "message": msg,
            "remote_video": video if video.startswith("http") else "",
            "remote_crop": crop if crop.startswith("http") else "",
        }

    @staticmethod
    def _make_uid(row: dict[str, Any]) -> str:
        raw = f"{row.get('camera_id')}|{row.get('event_type')}|{row.get('event_timestamp')}|{row.get('id')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _load_watermark(self) -> datetime:
        state_path = Path(__file__).resolve().parents[1] / "data" / "db_telegram_feeder_state.json"
        if state_path.exists():
            import json
            try:
                data = json.loads(state_path.read_text())
                ts_str = data.get("watermark") or data.get("last_id")
                if ts_str and isinstance(ts_str, str):
                    return datetime.fromisoformat(ts_str)
            except Exception:
                pass
        # Sin estado: procesar desde hace 5 minutos (eventos recientes no notificados)
        return datetime.now(timezone.utc) - timedelta(minutes=5)

    def _save_watermark(self, ts: datetime) -> None:
        import json
        state_path = Path(__file__).resolve().parents[1] / "data" / "db_telegram_feeder_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(ts, datetime):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)
        state_path.write_text(json.dumps({"watermark": ts_str}))

    def _download_url(self, url: str) -> Path:
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise FileNotFoundError(f"No es URL: {url}")
        suffix = PurePosixPath(url.split("?")[0]).suffix or (
            mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ".tmp"
        )
        key = hashlib.sha256(url.encode()).hexdigest()
        local = self._crop_cache_dir / f"{key}{suffix}"
        if local.exists() and local.stat().st_size > 0:
            return local
        part = local.with_suffix(local.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "RobiotecDashboard/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                with part.open("wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
        except Exception as exc:
            raise FileNotFoundError(f"No se pudo descargar {url}: {exc}") from exc
        part.replace(local)
        return local

    def _render_video(self, source_path: Path) -> Path:
        rendered = source_path.with_suffix(".telegram.mp4")
        if rendered.exists() and rendered.stat().st_size > 0:
            return rendered
        threads = max(1, int(self.settings.telegram_ffmpeg_threads or 1))
        part = rendered.with_suffix(rendered.suffix + ".part")
        cmd = [
            "ffmpeg", "-y", "-i", str(source_path),
            "-map", "0:v:0", "-an",
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast",
            "-threads", str(threads),
            "-filter_threads", str(threads),
            "-filter_complex_threads", str(threads),
            "-crf", "26", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-f", "mp4", str(part),
        ]
        with _FFMPEG_LOCK:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg falló")
        part.replace(rendered)
        return rendered

    def _set_status(self, **kw: Any) -> None:
        with self._lock:
            self._status.update(kw)

    @staticmethod
    def _psycopg_dsn(url: str) -> str:
        from urllib.parse import urlparse, urlunparse
        if url.startswith("postgresql+psycopg://"):
            url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        return urlunparse(urlparse(url))
