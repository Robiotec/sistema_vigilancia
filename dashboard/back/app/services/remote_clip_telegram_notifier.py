"""Notificador 24/7 de clips por Telegram — implementación robusta de producción.

Cambios internos respecto a la versión anterior:
  - Lee el manifest por SFTP incremental (ManifestSFTPReader) en lugar de
    ejecutar Python remoto cada ciclo.
  - Persiste eventos en camera_event_history (PostgreSQL) con ON CONFLICT.
  - Usa camera_alert_outbox (TelegramAlertWorker) como outbox transaccional:
    SELECT FOR UPDATE SKIP LOCKED, backoff exponencial, dead_letter.
  - No marca un evento como notificado hasta que Telegram confirma el envío.
  - En reinicios reanuda desde el cursor DB (no pierde eventos intermedios).
  - En primer arranque (sin cursor previo) avanza a EOF para no inundar Telegram.
  - Política SSH configurable: known_hosts + RejectPolicy si SSH_KNOWN_HOSTS_PATH
    existe; AutoAddPolicy como fallback (comportamiento anterior).

API pública sin cambios:
  start() / stop() / status() / check_once() / is_running
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlunparse, urlparse

import paramiko
import psycopg2
import psycopg2.extras
from psycopg2.extras import Json, execute_values

from back.app.config import Settings
from back.app.services.manifest_sftp_reader import ManifestSFTPReader
from back.app.services.send_telegram import (
    send_configured_telegram_photo,
    send_configured_telegram_text,
    send_configured_telegram_video,
)
from back.app.services.telegram_alert_worker import TelegramAlertWorker

_log = logging.getLogger(__name__)
ECUADOR_TZ = timezone(timedelta(hours=-5))
VIDEO_EVENT_TYPES = {"clip", "clips_movimiento", "clips_zona"}
TELEGRAM_EVENT_LABELS = {
    "clip": "zona",
    "clips_movimiento": "movimiento",
    "clips_zona": "zona",
}
_FFMPEG_RENDER_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ClipAlert:
    uid: str           # SHA-256 del uid_source (para compatibilidad interna)
    event_type: str
    cam_id: str
    timestamp: int
    crop_path: str
    video_path: str
    json_path: str
    track_id: str
    payload: dict[str, Any]
    manifest_payload: dict[str, Any]


class RemoteClipTelegramNotifier:
    """Vigila el manifest remoto y envía por Telegram nuevos eventos de video."""

    def __init__(self, settings: Settings, *, poll_interval: float = 3.0) -> None:
        self.settings = settings
        self.poll_interval = max(1.0, float(poll_interval))

        self.data_dir = Path(__file__).resolve().parents[1] / "data"
        self.crop_cache_dir = self.data_dir / "telegram_clip_crops"

        # Lector incremental del manifest
        manifest_path = str(PurePosixPath(settings.ssh_events_base_path) / "manifest.jsonl")
        self._manifest_reader = ManifestSFTPReader(settings, "main", manifest_path)

        # Worker de outbox
        self._worker = TelegramAlertWorker(
            db_dsn=self._psycopg_dsn(settings.database_url),
            send_video_fn=lambda msg, path: send_configured_telegram_video(message=msg, video_path=path),
            send_photo_fn=lambda msg, path: send_configured_telegram_photo(message=msg, image_path=path),
            send_text_fn=lambda msg: send_configured_telegram_text(message=msg),
            cache_remote_file_fn=self._cache_remote_file,
            render_video_fn=self._render_telegram_video,
        )

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "running": False,
            "last_error": "",
            "last_checked_at": "",
            "last_notified_uid": "",
            "last_notified_at": "",
            "last_sent_total": 0,
            "last_delivery_detail": "",
            "last_video_path": "",
            "last_rendered_video_path": "",
            "outbox_pending": 0,
        }

    # ------------------------------------------------------------------ public

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="remote-clip-telegram-notifier",
            daemon=True,
        )
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

    def check_once(self, *, seed_existing: bool = False) -> dict[str, Any]:
        """Un ciclo completo: leer manifest → persistir → outbox → Telegram.

        seed_existing=True solo tiene efecto cuando no existe cursor previo en DB:
        en ese caso avanza el cursor a EOF sin enviar alertas (evita flood inicial).
        Con cursor ya existente, seed_existing se ignora y se procesan los eventos
        pendientes desde el último offset guardado (recupera eventos entre reinicios).
        """
        now_iso = self._iso_now()
        self._set_status(last_checked_at=now_iso, last_error="")

        # --- 1. Leer nuevas líneas del manifest via SFTP ---
        try:
            with self._sftp_connection() as (_, sftp):
                if seed_existing and self._manifest_reader.current_offset() == 0:
                    seeded = self._manifest_reader.seed_to_end(sftp)
                    return {"checked": seeded, "sent": 0, "seeded": seeded}
                new_rows, new_cursor = self._manifest_reader.read_new_lines(sftp)
        except Exception as exc:
            self._set_status(last_error=str(exc))
            raise

        if not new_rows:
            # Drenar outbox siempre para reintentar fallos reales. No se relee
            # el tail del manifest: eso puede volver a tomar eventos historicos.
            sent = self._worker.drain()
            if sent:
                self._set_status(last_sent_total=sent)
            self._set_status(outbox_pending=self._worker.pending_count())
            return {"checked": 0, "sent": sent, "skipped": 0, "recovered": 0}

        # --- 2. Filtrar eventos de video ---
        clips = self._parse_clip_rows(new_rows)

        # --- 3. Persistir en camera_event_history (idempotente) ---
        persist_ok = True
        try:
            self._persist_and_enqueue_clips(clips)
        except Exception as exc:
            _log.error("[notifier] error persistiendo clips nuevos: %s", exc)
            self._set_status(last_error=str(exc))
            persist_ok = False

        # --- 5. Avanzar cursor SOLO si la persistencia fue exitosa ---
        if persist_ok and new_cursor:
            self._manifest_reader.save_cursor(new_cursor)

        # --- 6. Drenar outbox siempre ---
        sent = self._worker.drain()

        if sent > 0:
            self._set_status(
                last_sent_total=sent,
                last_notified_at=self._iso_now(),
            )
        self._set_status(outbox_pending=self._worker.pending_count())

        return {"checked": len(clips), "sent": sent, "skipped": len(new_rows) - len(clips)}

    # ----------------------------------------------------------------- loop

    def _run_loop(self) -> None:
        seeded = False
        while not self._stop_event.is_set():
            try:
                self.check_once(seed_existing=not seeded)
                seeded = True
            except Exception as exc:
                self._set_status(last_error=str(exc), last_checked_at=self._iso_now())
            finally:
                self._stop_event.wait(self.poll_interval)
        self._set_status(running=False)

    # ---------------------------------------------------------------- parsing

    def _parse_clip_rows(self, rows: list[dict[str, Any]]) -> list[ClipAlert]:
        clips: list[ClipAlert] = []
        base = self.settings.ssh_events_base_path
        for row in rows:
            event_type = str(row.get("type") or "").strip()
            if event_type not in VIDEO_EVENT_TYPES:
                continue
            cam_id = str(row.get("cam_id") or "").strip()
            if not cam_id:
                continue

            timestamp = self._int_value(row.get("ts") or row.get("timestamp"))
            video_path = str(row.get("clip_file") or row.get("file") or "").strip()
            crop_path = str(
                row.get("crop_path") or row.get("crop_file") or row.get("crop") or ""
            ).strip()
            json_path = str(row.get("json_file") or "").strip()
            track_id = str(row.get("track_id") or "").strip()

            video_path = self._resolve_remote_path(base, cam_id, video_path)
            crop_path = self._resolve_remote_path(base, cam_id, crop_path)
            if json_path:
                json_path = self._resolve_remote_path(base, cam_id, json_path)

            uid_source = "|".join([cam_id, event_type, str(timestamp), track_id, crop_path, video_path, json_path])
            uid = hashlib.sha256(uid_source.encode("utf-8")).hexdigest()

            clips.append(ClipAlert(
                uid=uid,
                event_type=event_type,
                cam_id=cam_id,
                timestamp=timestamp,
                crop_path=crop_path,
                video_path=video_path,
                json_path=json_path,
                track_id=track_id,
                payload={},
                manifest_payload=row,
            ))
        return clips

    @staticmethod
    def _resolve_remote_path(base: str, cam_id: str, raw: str) -> str:
        if not raw:
            return ""
        path = PurePosixPath(raw)
        if path.is_absolute():
            return raw

        base_path = PurePosixPath(base)
        parts = path.parts
        if parts and parts[0] == base_path.name:
            path = PurePosixPath(*parts[1:]) if len(parts) > 1 else PurePosixPath(".")
            parts = path.parts

        if parts and parts[0] == cam_id:
            return str(base_path / path)
        return str(base_path / cam_id / path)

    # ---------------------------------------------------------- DB persistence

    def _persist_clip_events(self, clips: list[ClipAlert]) -> list[str | None]:
        """Inserta clips en camera_event_history. Devuelve lista de event_uid en orden."""
        if not clips:
            return []
        uids: list[str | None] = []
        try:
            with self._db_connection() as conn:
                with conn.cursor() as cur:
                    for clip in clips:
                        row = self._clip_to_history_row(clip)
                        if row is None:
                            uids.append(None)
                            continue
                        cur.execute(
                            """
                            INSERT INTO camera_event_history (
                                event_type, event_category, origin,
                                camera_id, camera_name,
                                event_timestamp, detected_at, detected_date,
                                title, description,
                                person_id, person_name, plate, track_id,
                                status, severity,
                                manifest_file_path, json_file_path, video_file_path,
                                image_file_path, crop_path,
                                manifest_payload, detail_payload
                            )
                            VALUES (
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s
                            )
                            ON CONFLICT ON CONSTRAINT uq_camera_event_history_event_uid
                            DO UPDATE SET updated_at = now()
                            RETURNING event_uid
                            """,
                            row,
                        )
                        result = cur.fetchone()
                        uids.append(result[0] if result else None)
                conn.commit()
        except Exception as exc:
            _log.error("[notifier] error persistiendo clips: %s", exc)
            return [None] * len(clips)
        return uids

    def _camera_notif_flags(self, cam_ids: set[str]) -> dict[str, dict[str, bool]]:
        """Query notification_telegram and notification_email for a batch of camera IDs.

        Returns {cam_id: {telegram: bool, email: bool}}. Unknown cameras default to True.
        """
        if not cam_ids:
            return {}
        try:
            with psycopg2.connect(self._psycopg_dsn(self.settings.database_url)) as conn:
                with conn.cursor() as cur:
                    placeholders = ",".join(["%s"] * len(cam_ids))
                    ids = list(cam_ids)
                    cur.execute(
                        f"""
                        SELECT unique_code, name,
                               COALESCE(notification_telegram, true) AS notif_tg,
                               COALESCE(notification_email, true)    AS notif_em
                        FROM cameras
                        WHERE (unique_code = ANY(%s) OR name = ANY(%s))
                          AND deleted_at IS NULL
                        """,
                        (ids, ids),
                    )
                    rows = cur.fetchall()
            result: dict[str, dict[str, bool]] = {}
            for unique_code, name, notif_tg, notif_em in rows:
                flags = {"telegram": bool(notif_tg), "email": bool(notif_em)}
                if unique_code:
                    result[unique_code] = flags
                if name:
                    result[name] = flags
            return result
        except Exception as exc:
            _log.warning("[notifier] no se pudo leer flags de notificacion: %s", exc)
            return {}

    def _persist_and_enqueue_clips(self, clips: list[ClipAlert]) -> int:
        if not clips:
            return 0
        event_uids = self._persist_clip_events(clips)

        # Fetch per-camera notification flags once for the whole batch
        cam_ids = {c.cam_id for c in clips if c.cam_id}
        notif_flags = self._camera_notif_flags(cam_ids)

        inserted_count = 0
        for clip, uid in zip(clips, event_uids):
            if not uid:
                continue
            flags = notif_flags.get(clip.cam_id, {"telegram": True, "email": True})
            if not flags.get("telegram", True):
                _log.info(
                    "[notifier] Telegram desactivado para cam=%s — evento omitido", clip.cam_id
                )
                continue
            if not self._should_enqueue_clip(clip):
                continue
            payload = self._build_outbox_payload(clip)
            if self._worker.insert_pending(uid, clip.cam_id, clip.event_type, payload):
                inserted_count += 1
        return inserted_count

    def _should_enqueue_clip(self, clip: ClipAlert) -> bool:
        max_age = self._telegram_max_event_age_seconds()
        if max_age <= 0 or clip.timestamp <= 0:
            return True
        event_at = datetime.fromtimestamp(clip.timestamp, tz=timezone.utc)
        age = datetime.now(timezone.utc) - event_at
        if age.total_seconds() <= max_age:
            return True
        _log.info(
            "[notifier] evento omitido para Telegram por antiguedad: cam=%s type=%s ts=%s age=%ss max=%ss",
            clip.cam_id,
            clip.event_type,
            clip.timestamp,
            int(age.total_seconds()),
            max_age,
        )
        return False

    def _clip_to_history_row(self, clip: ClipAlert) -> tuple[Any, ...] | None:
        if not clip.cam_id:
            return None
        timestamp = clip.timestamp or 0
        detected_at = (
            datetime.fromtimestamp(timestamp, tz=ECUADOR_TZ)
            if timestamp > 0
            else datetime.now(ECUADOR_TZ)
        )
        track_id_int = self._int_value(clip.track_id) if clip.track_id else 0
        video_path = clip.video_path or None
        crop_path = clip.crop_path or None
        json_path = clip.json_path if clip.json_path and clip.json_path.endswith(".json") else None

        return (
            clip.event_type,           # event_type
            self._event_category(clip.event_type),  # event_category
            "fixed_camera",            # origin
            clip.cam_id,               # camera_id
            None,                      # camera_name (no disponible desde manifest)
            timestamp if timestamp > 0 else None,   # event_timestamp
            detected_at,               # detected_at
            detected_at.date(),        # detected_date
            self._event_title(clip.event_type),  # title
            None,                      # description
            None,                      # person_id
            None,                      # person_name
            None,                      # plate
            track_id_int,              # track_id
            "new",                     # status
            "info",                    # severity
            None,                      # manifest_file_path
            json_path,                 # json_file_path
            video_path,                # video_file_path
            None,                      # image_file_path
            crop_path,                 # crop_path
            Json(clip.manifest_payload),   # manifest_payload
            Json(clip.payload),            # detail_payload
        )

    def _build_outbox_payload(self, clip: ClipAlert) -> dict[str, Any]:
        return {
            "message": self._message_for_clip(clip),
            "remote_video": clip.video_path or "",
            "remote_crop": clip.crop_path or "",
        }

    # --------------------------------------------------------- SSH / SFTP

    @contextmanager
    def _sftp_connection(self):
        client = self._make_ssh_client()
        sftp = client.open_sftp()
        try:
            yield client, sftp
        finally:
            try:
                sftp.close()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass

    def _make_ssh_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        known_hosts = str(self.settings.ssh_known_hosts_path or "").strip()
        key_path = str(self.settings.ssh_key_path or "").strip()

        if known_hosts and Path(known_hosts).exists():
            client.load_host_keys(known_hosts)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            if known_hosts:
                _log.warning(
                    "[ssh] SSH_KNOWN_HOSTS_PATH '%s' no existe — usando AutoAddPolicy",
                    known_hosts,
                )
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": self.settings.ssh_events_host,
            "username": self.settings.ssh_events_user,
            "port": self.settings.ssh_events_port,
            "timeout": 10,
        }
        if key_path and Path(key_path).exists():
            connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key_file(key_path)
        else:
            connect_kwargs["password"] = self.settings.ssh_events_password

        client.connect(**connect_kwargs)
        return client

    # Mantener _client() para compatibilidad interna con _cache_remote_file
    def _client(self) -> "_SSHClientContext":
        return _SSHClientContext(self._make_ssh_client())

    # --------------------------------------------------------- file cache

    def _cache_remote_file(self, remote_path: str) -> Path:
        normalized_path = str(PurePosixPath(remote_path or "")).strip()
        if not normalized_path:
            raise FileNotFoundError("Ruta remota vacía")

        suffix = PurePosixPath(normalized_path).suffix or (
            mimetypes.guess_extension(mimetypes.guess_type(normalized_path)[0] or "") or ".jpg"
        )
        cache_key = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
        local_path = self.crop_cache_dir / f"{cache_key}{suffix}"
        partial_path = local_path.with_suffix(f"{local_path.suffix}.part")

        self.crop_cache_dir.mkdir(parents=True, exist_ok=True)
        if local_path.exists() and local_path.stat().st_size > 0:
            return local_path

        with self._client() as client:
            with client.open_sftp() as sftp:
                self._wait_remote_file_stable(sftp, normalized_path)
                with sftp.open(normalized_path, "rb") as remote_file:
                    with partial_path.open("wb") as local_file:
                        while True:
                            chunk = remote_file.read(1024 * 1024)
                            if not chunk:
                                break
                            local_file.write(chunk)
                partial_path.replace(local_path)
        return local_path

    @staticmethod
    def _wait_remote_file_stable(sftp: paramiko.SFTPClient, normalized_path: str) -> None:
        previous_size = -1
        stable_reads = 0
        for _ in range(8):
            stat_result = sftp.stat(normalized_path)
            size = int(getattr(stat_result, "st_size", 0) or 0)
            if size > 0 and size == previous_size:
                stable_reads += 1
                if stable_reads >= 2:
                    return
            else:
                stable_reads = 0
            previous_size = size
            time.sleep(0.75)

    # --------------------------------------------------------- video render

    def _render_telegram_video(self, source_path: Path) -> Path:
        rendered_path = source_path.with_suffix(".telegram.mp4")
        if rendered_path.exists() and rendered_path.stat().st_size > 0:
            return rendered_path

        threads = self._ffmpeg_threads()
        partial_path = rendered_path.with_suffix(f"{rendered_path.suffix}.part")
        command = [
            "ffmpeg", "-y", "-i", str(source_path),
            "-map", "0:v:0", "-an",
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast",
            "-threads", str(threads),
            "-filter_threads", str(threads),
            "-filter_complex_threads", str(threads),
            "-crf", "26", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-f", "mp4",
            str(partial_path),
        ]
        with _FFMPEG_RENDER_LOCK:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "No se pudo renderizar el video para Telegram")
        partial_path.replace(rendered_path)
        if rendered_path.stat().st_size > 45 * 1024 * 1024:
            return self._render_small_telegram_video(source_path, rendered_path)
        return rendered_path

    def _render_small_telegram_video(self, source_path: Path, rendered_path: Path) -> Path:
        small_path = source_path.with_suffix(".telegram-small.mp4")
        if small_path.exists() and small_path.stat().st_size > 0:
            return small_path

        threads = self._ffmpeg_threads()
        partial_path = small_path.with_suffix(f"{small_path.suffix}.part")
        command = [
            "ffmpeg", "-y", "-i", str(source_path),
            "-map", "0:v:0", "-an",
            "-vf", "scale='min(854,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast",
            "-threads", str(threads),
            "-filter_threads", str(threads),
            "-filter_complex_threads", str(threads),
            "-crf", "32", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-f", "mp4",
            str(partial_path),
        ]
        with _FFMPEG_RENDER_LOCK:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "No se pudo reducir el video para Telegram")
        partial_path.replace(small_path)
        try:
            rendered_path.unlink()
        except OSError:
            pass
        return small_path

    # --------------------------------------------------------- helpers

    def _ffmpeg_threads(self) -> int:
        try:
            return max(1, min(2, int(self.settings.telegram_ffmpeg_threads or 1)))
        except (TypeError, ValueError):
            return 1

    def _telegram_max_event_age_seconds(self) -> int:
        try:
            return max(0, int(self.settings.telegram_max_event_age_seconds or 0))
        except (TypeError, ValueError):
            return 3600

    def _message_for_clip(self, clip: ClipAlert) -> str:
        detected_at = "Sin dato"
        if clip.timestamp:
            detected_at = datetime.fromtimestamp(clip.timestamp, tz=ECUADOR_TZ).strftime("%d/%m/%Y %H:%M:%S")
        event_label = TELEGRAM_EVENT_LABELS.get(clip.event_type, clip.event_type or "Sin dato")
        rows = [
            "ALERTA",
            "",
            "",
            f"Tipo de evento: {event_label}",
            f"Camara: {clip.cam_id or 'Sin dato'}",
            f"Hora: {detected_at}",
        ]
        if clip.track_id:
            rows.append(f"Track ID: {clip.track_id}")
        if clip.video_path:
            rows.append(f"Video: {PurePosixPath(clip.video_path).name}")
        return "\n".join(rows)

    @staticmethod
    def _event_title(event_type: str) -> str:
        return {
            "clip": "Video de zona detectado",
            "clips_movimiento": "Movimiento detectado",
            "clips_zona": "Alerta de zona detectada",
        }.get(event_type, "Video detectado")

    @staticmethod
    def _event_category(event_type: str) -> str:
        return {
            "clips_zona": "alerta",
        }.get(event_type, "movimiento")

    @staticmethod
    def _delivery_detail(delivery: dict[str, Any]) -> str:
        results = delivery.get("results") if isinstance(delivery.get("results"), list) else []
        if not results:
            return ""
        return "; ".join(
            f"{item.get('chat_id')}: {item.get('detail')}"
            for item in results
            if isinstance(item, dict)
        )

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)

    def _db_connection(self):
        return psycopg2.connect(self._psycopg_dsn(self.settings.database_url))

    @staticmethod
    def _psycopg_dsn(database_url: str) -> str:
        if database_url.startswith("postgresql+psycopg://"):
            return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        return database_url

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()


class _SSHClientContext:
    def __init__(self, client: paramiko.SSHClient) -> None:
        self.client = client

    def __enter__(self) -> paramiko.SSHClient:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()
