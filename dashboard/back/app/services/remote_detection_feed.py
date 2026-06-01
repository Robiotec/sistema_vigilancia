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

import paramiko
import psycopg2
from psycopg2.extras import Json, execute_values

from back.app.config import Settings

ECUADOR_TZ = timezone(timedelta(hours=-5))


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
        if self.event_type in {"clip", "click"}:
            return {
                "event_type": self.event_type,
                "cam_id": self.cam_id,
                "timestamp": self.timestamp,
                "source_file": self.source_file,
                "crop_path": self.crop_path,
                "video_path": self.video_path,
                "track_id": str(payload.get("track_id") or "").strip(),
                "display_title": "Video detectado",
                "rows": self._clip_rows(payload),
            }

        if self.event_type == "person":
            raw_name = str(payload.get("person_name") or "").strip()
            parts = raw_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            extra_info = payload.get("person_info") if isinstance(payload.get("person_info"), dict) else {}
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
                "rows": [
                    {"label": "nombre", "value": extra_info.get("nombre") or first_name or raw_name or "Sin dato"},
                    {"label": "apellido", "value": extra_info.get("apellido") or last_name or "Sin dato"},
                    {"label": "Cedula", "value": str(payload.get("person_id") or extra_info.get("cedula") or "Sin dato")},
                ],
            }

        vehicle_info = payload.get("vehicle_info") if isinstance(payload.get("vehicle_info"), dict) else {}
        return {
            "event_type": self.event_type,
            "cam_id": self.cam_id,
            "timestamp": self.timestamp,
            "source_file": self.source_file,
            "crop_path": self.crop_path,
            "video_path": self.video_path,
            "plate": str(payload.get("plate") or "").strip(),
            "display_title": "Vehículo detectado",
            "rows": [
                {"label": "placa", "value": str(payload.get("plate") or vehicle_info.get("Placa") or "Sin dato")},
                {"label": "marca", "value": str(vehicle_info.get("Marca") or "Sin dato")},
                {"label": "modelo", "value": str(vehicle_info.get("Modelo") or "Sin dato")},
            ],
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

        remote_python = f"""
import json
from pathlib import Path

base = Path({self.settings.ssh_events_base_path!r})
manifest = base / "manifest.jsonl"
cam_id = {normalized_cam_id!r}
limit = {max(1, min(int(limit), 24))}
items = []

def resolve_path(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates = [
            base / cam_id / raw,
            base / raw,
            path,
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

if manifest.exists():
    with manifest.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("cam_id") or "").strip() != cam_id:
                continue
            event_type = str(row.get("type") or "").strip()
            if event_type in {{"clip", "click"}}:
                video_file = resolve_path(row.get("clip_file") or row.get("file"))
                json_file = resolve_path(row.get("json_file"))
                if not video_file or not video_file.exists():
                    continue
                payload = dict(row)
                if json_file and json_file.exists():
                    try:
                        loaded_payload = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
                        if isinstance(loaded_payload, dict):
                            payload.update(loaded_payload)
                    except Exception:
                        pass
                payload["track_id"] = payload.get("track_id") or row.get("track_id")
                items.append({{
                    "event_type": event_type,
                    "cam_id": cam_id,
                    "timestamp": int(payload.get("timestamp") or row.get("ts") or 0),
                    "source_file": str(json_file or video_file),
                    "crop_path": "",
                    "video_path": str(video_file),
                    "manifest_payload": row,
                    "payload": payload,
                }})
                continue
            source_file = resolve_path(row.get("file"))
            if not source_file or not source_file.exists():
                continue
            try:
                payload = json.loads(source_file.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            items.append({{
                "event_type": str(row.get("type") or "").strip(),
                "cam_id": cam_id,
                "timestamp": int(row.get("ts") or payload.get("timestamp") or 0),
                "source_file": str(source_file),
                "crop_path": str(payload.get("crop_path") or ""),
                "video_path": "",
                "manifest_payload": row,
                "payload": payload,
            }})

print(json.dumps({{"items": items[-limit:], "history_items": items}}, ensure_ascii=False))
"""
        output = self._run_python(remote_python)
        if not output:
            return []

        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return []

        if isinstance(parsed, dict):
            items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
            history_items = parsed.get("history_items") if isinstance(parsed.get("history_items"), list) else items
        else:
            items = parsed if isinstance(parsed, list) else []
            history_items = items

        events = [
            RemoteCameraEvent(
                event_type=str(item.get("event_type") or "").strip(),
                cam_id=str(item.get("cam_id") or "").strip(),
                timestamp=int(item.get("timestamp") or 0),
                source_file=str(item.get("source_file") or "").strip(),
                crop_path=str(item.get("crop_path") or "").strip(),
                video_path=str(item.get("video_path") or "").strip(),
                payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
            )
            for item in items
        ]
        events.sort(key=lambda event: event.timestamp, reverse=True)
        rendered_events = [event.to_dict() for event in events]
        try:
            self._persist_events(history_items)
        except Exception:
            pass
        self._warm_recent_videos(rendered_events)
        return rendered_events

    def read_remote_file(self, remote_path: str) -> tuple[bytes, str]:
        normalized_path = str(PurePosixPath(remote_path or "")).strip()
        if not normalized_path:
            raise FileNotFoundError("Ruta remota vacía")

        with self._client() as client:
            with client.open_sftp() as sftp:
                with sftp.open(normalized_path, "rb") as remote_file:
                    content = remote_file.read()
        media_type, _ = mimetypes.guess_type(normalized_path)
        return content, media_type or "application/octet-stream"

    def cache_remote_video(self, remote_path: str) -> tuple[Path, str]:
        normalized_path = str(PurePosixPath(remote_path or "")).strip()
        if not normalized_path:
            raise FileNotFoundError("Ruta remota vacía")

        with self._cache_lock(normalized_path):
            return self._cache_remote_video_locked(normalized_path)

    def _cache_remote_video_locked(self, normalized_path: str) -> tuple[Path, str]:
        suffix = PurePosixPath(normalized_path).suffix or ".mp4"
        cache_key = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
        source_path = self.video_cache_dir / f"{cache_key}{suffix}"
        browser_path = self.video_cache_dir / f"{cache_key}.browser.mp4"
        partial_path = source_path.with_suffix(f"{source_path.suffix}.part")

        self.video_cache_dir.mkdir(parents=True, exist_ok=True)
        if not source_path.exists() or source_path.stat().st_size == 0:
            with self._client() as client:
                with client.open_sftp() as sftp:
                    sftp.stat(normalized_path)
                    with sftp.open(normalized_path, "rb") as remote_file:
                        with partial_path.open("wb") as local_file:
                            while True:
                                chunk = remote_file.read(1024 * 1024)
                                if not chunk:
                                    break
                                local_file.write(chunk)
                    partial_path.replace(source_path)

        if self._is_browser_video(source_path):
            return source_path, "video/mp4"

        self._ensure_browser_video(source_path, browser_path)
        return browser_path, "video/mp4"

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

    def _persist_events(self, items: list[dict[str, Any]]) -> None:
        rows = [self._history_row(item) for item in items]
        rows = [row for row in rows if row is not None]
        if not rows:
            return

        query = """
            INSERT INTO camera_event_history (
                event_type,
                event_category,
                origin,
                camera_id,
                camera_name,
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
                manifest_file_path,
                json_file_path,
                video_file_path,
                image_file_path,
                crop_path,
                manifest_payload,
                detail_payload
            )
            VALUES %s
            ON CONFLICT ON CONSTRAINT uq_camera_event_history_event_uid DO UPDATE SET
                event_category = EXCLUDED.event_category,
                origin = EXCLUDED.origin,
                camera_name = EXCLUDED.camera_name,
                detected_at = EXCLUDED.detected_at,
                detected_date = EXCLUDED.detected_date,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                person_id = EXCLUDED.person_id,
                person_name = EXCLUDED.person_name,
                plate = EXCLUDED.plate,
                track_id = EXCLUDED.track_id,
                severity = EXCLUDED.severity,
                manifest_file_path = EXCLUDED.manifest_file_path,
                json_file_path = EXCLUDED.json_file_path,
                video_file_path = EXCLUDED.video_file_path,
                image_file_path = EXCLUDED.image_file_path,
                crop_path = EXCLUDED.crop_path,
                manifest_payload = EXCLUDED.manifest_payload,
                detail_payload = EXCLUDED.detail_payload,
                updated_at = now()
        """
        with self._db_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, rows)
            conn.commit()

    def _history_row(self, item: dict[str, Any]) -> tuple[Any, ...] | None:
        event_type = str(item.get("event_type") or "").strip()
        camera_id = str(item.get("cam_id") or "").strip()
        if not event_type or not camera_id:
            return None

        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        manifest_payload = (
            item.get("manifest_payload") if isinstance(item.get("manifest_payload"), dict) else {}
        )
        timestamp = self._int_value(item.get("timestamp") or payload.get("timestamp") or manifest_payload.get("ts"))
        detected_at = datetime.fromtimestamp(timestamp, tz=ECUADOR_TZ) if timestamp else datetime.now(ECUADOR_TZ)

        video_path = str(item.get("video_path") or payload.get("clip_path") or "").strip() or None
        source_file = str(item.get("source_file") or "").strip() or None
        crop_path = str(item.get("crop_path") or payload.get("crop_path") or "").strip() or None
        image_file_path = self._first_text(payload, ("image_path", "source_image", "image_file", "frame_path"))

        person_id = self._first_text(payload, ("person_id",)) or self._first_text(manifest_payload, ("person_id",))
        person_name = self._first_text(payload, ("person_name", "name"))
        plate = self._first_text(payload, ("plate", "placa"))
        track_id = self._int_value(payload.get("track_id") or manifest_payload.get("track_id"))

        return (
            event_type,
            self._event_category(event_type),
            "fixed_camera",
            camera_id,
            self._camera_name(camera_id),
            timestamp,
            detected_at,
            detected_at.date(),
            self._event_title(event_type),
            self._event_description(event_type, payload),
            person_id,
            person_name,
            plate,
            track_id,
            "new",
            self._event_severity(event_type),
            None,
            source_file if source_file and source_file.endswith(".json") else None,
            video_path,
            image_file_path,
            crop_path,
            Json(manifest_payload),
            Json(payload),
        )

    def _db_connection(self):
        return psycopg2.connect(self._psycopg_dsn(self.settings.database_url))

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
        }.get(event_type, event_type)

    @staticmethod
    def _event_title(event_type: str) -> str:
        return {
            "person": "Persona detectada",
            "plate": "Vehiculo detectado",
            "clip": "Video detectado",
            "click": "Video detectado",
        }.get(event_type, "Evento detectado")

    @staticmethod
    def _event_description(event_type: str, payload: dict[str, Any]) -> str | None:
        if event_type in {"clip", "click"} and payload.get("duration") is not None:
            return f"Clip de video generado con duracion {payload.get('duration')} s."
        return None

    @staticmethod
    def _event_severity(event_type: str) -> str:
        return "info" if event_type in {"person", "plate", "clip", "click"} else "warning"

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

    def _run_python(self, script: str) -> str:
        command = "python3 - <<'PY'\n" + script.strip() + "\nPY"
        with self._client() as client:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise RuntimeError(error or f"Comando remoto falló con código {exit_status}")
        return output

    def _client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.settings.ssh_events_host,
            username=self.settings.ssh_events_user,
            password=self.settings.ssh_events_password,
            port=self.settings.ssh_events_port,
            timeout=10,
        )
        return _SSHClientContext(client)


class _SSHClientContext:
    def __init__(self, client: paramiko.SSHClient) -> None:
        self.client = client

    def __enter__(self) -> paramiko.SSHClient:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()
