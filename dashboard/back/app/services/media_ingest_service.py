"""Worker continuo que vigila manifest.jsonl en el servidor AI y sube media a MinIO."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

import paramiko
import psycopg2
from minio import Minio
from minio.error import S3Error
from psycopg2.extras import Json, execute_values

from back.app.config import Settings, get_settings

logger = logging.getLogger(__name__)

ECUADOR_TZ = timezone(timedelta(hours=-5))
VIDEO_EVENT_TYPES = {"clip", "click", "clips_movimiento", "clips_zona"}

STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "manifest_ingest_state.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def _int_val(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _event_category(event_type: str) -> str:
    return {
        "plate": "vehiculo",
        "person": "reconocimiento_facial",
        "clip": "movimiento",
        "clips_zona": "movimiento",
        "clips_movimiento": "movimiento",
        "click": "movimiento",
    }.get(event_type, "alerta")


def _event_title(event_type: str) -> str:
    return {
        "plate": "Vehículo detectado",
        "person": "Persona detectada",
        "clip": "Video de zona detectado",
        "clips_zona": "Zona activa detectada",
        "clips_movimiento": "Movimiento detectado",
    }.get(event_type, "Evento detectado")


def _event_severity(event_type: str) -> str:
    return "warning" if event_type in VIDEO_EVENT_TYPES else "info"


def _object_key(event_type: str, cam_id: str, filename: str) -> str:
    prefix = {
        "plate": "plates",
        "person": "persons",
        "clip": "clips",
        "clips_zona": "clips",
        "clips_movimiento": "clips",
        "click": "clips",
    }.get(event_type, "misc")
    return f"{prefix}/{cam_id}/{filename}"


def _public_url(endpoint: str, bucket: str, key: str, secure: bool) -> str:
    scheme = "https" if secure else "http"
    return f"{scheme}://{endpoint}/{bucket}/{key}"


# ── SSH/SFTP ─────────────────────────────────────────────────────────────────

class SSHPool:
    def __init__(self, settings: Settings):
        self._s = settings
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def _connect(self) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._s.ssh_events_host,
            port=self._s.ssh_events_port,
            username=self._s.ssh_events_user,
            password=self._s.ssh_events_password,
            timeout=15,
            look_for_keys=False,
            allow_agent=False,
        )
        self._client = client
        self._sftp = client.open_sftp()

    def sftp(self) -> paramiko.SFTPClient:
        if self._sftp is None or self._client is None:
            self._connect()
        try:
            self._sftp.stat(".")  # type: ignore[union-attr]
        except Exception:
            self._connect()
        return self._sftp  # type: ignore[return-value]

    def read_file_bytes(self, remote_path: str) -> bytes:
        buf = io.BytesIO()
        self.sftp().getfo(remote_path, buf)
        return buf.getvalue()

    def read_manifest_tail(self, manifest_path: str, from_offset: int) -> tuple[list[str], int]:
        sftp = self.sftp()
        try:
            stat = sftp.stat(manifest_path)
            size = stat.st_size or 0
        except FileNotFoundError:
            return [], from_offset

        if size <= from_offset:
            return [], from_offset

        with sftp.open(manifest_path, "rb") as fh:
            fh.seek(from_offset)
            chunk = fh.read(size - from_offset)

        text = chunk.decode("utf-8", errors="replace")
        lines = [l for l in text.splitlines() if l.strip()]
        new_offset = from_offset + len(chunk)
        return lines, new_offset

    def close(self) -> None:
        try:
            if self._sftp:
                self._sftp.close()
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._sftp = None
        self._client = None


# ── MinIO ─────────────────────────────────────────────────────────────────────

class MinIOUploader:
    def __init__(self, settings: Settings):
        self._s = settings
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                # Política pública de lectura
                policy = json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self._bucket}/*"],
                    }]
                })
                self._client.set_bucket_policy(self._bucket, policy)
                logger.info("[MinIO] Bucket '%s' creado con política pública.", self._bucket)
        except S3Error as exc:
            logger.warning("[MinIO] No se pudo verificar/crear bucket: %s", exc)

    def upload_bytes(self, data: bytes, object_key: str, content_type: str | None = None) -> str:
        if not content_type:
            content_type, _ = mimetypes.guess_type(object_key)
            content_type = content_type or "application/octet-stream"
        self._client.put_object(
            self._bucket,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return _public_url(
            self._s.minio_public_endpoint,
            self._bucket,
            object_key,
            self._s.minio_secure,
        )

    def object_exists(self, object_key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, object_key)
            return True
        except S3Error:
            return False


# ── Estado ────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"offset": 0, "processed": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


# ── Worker ────────────────────────────────────────────────────────────────────

class MediaIngestService:
    def __init__(self, settings: Settings | None = None):
        self._s = settings or get_settings()
        self._ssh = SSHPool(self._s)
        self._minio = MinIOUploader(self._s)
        self._manifest = str(
            PurePosixPath(self._s.ssh_events_base_path) / "manifest.jsonl"
        )

    def run_forever(self, poll_interval: float = 4.0) -> None:
        logger.info("[MediaIngest] Iniciando — manifest: %s", self._manifest)
        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                logger.info("[MediaIngest] Detenido.")
                break
            except Exception as exc:
                logger.error("[MediaIngest] Error en ciclo: %s", exc, exc_info=True)
                time.sleep(10)
            time.sleep(poll_interval)

    def _tick(self) -> int:
        state = _load_state()
        lines, new_offset = self._ssh.read_manifest_tail(self._manifest, state["offset"])
        if not lines:
            return 0

        processed = 0
        rows: list[tuple] = []
        for line in lines:
            row = self._process_line(line)
            if row:
                rows.append(row)
                processed += 1

        if rows:
            self._insert_rows(rows)

        state["offset"] = new_offset
        state["processed"] = state.get("processed", 0) + processed
        _save_state(state)

        if processed:
            logger.info("[MediaIngest] %d evento(s) nuevos procesados.", processed)
        return processed

    def _process_line(self, line: str) -> tuple | None:
        try:
            entry = json.loads(line)
        except Exception:
            return None

        event_type = str(entry.get("type") or "").strip()
        cam_id = str(entry.get("cam_id") or "").strip()
        if not event_type or not cam_id:
            return None

        ts = _int_val(entry.get("ts")) or 0
        detected_at = datetime.fromtimestamp(ts, tz=ECUADOR_TZ) if ts else datetime.now(ECUADOR_TZ)

        base = self._s.ssh_events_base_path

        if event_type in VIDEO_EVENT_TYPES:
            clip_remote = str(entry.get("clip_file") or entry.get("file") or "")
            json_remote = str(entry.get("json_file") or "")
            payload = dict(entry)

            # Leer JSON de detalle si existe
            if json_remote:
                try:
                    data = self._ssh.read_file_bytes(json_remote)
                    loaded = json.loads(data)
                    if isinstance(loaded, dict):
                        payload.update(loaded)
                except Exception:
                    pass

            video_url = self._upload_remote(clip_remote, event_type, cam_id) if clip_remote else None
            track_id = _int_val(payload.get("track_id") or entry.get("track_id"))

            return self._build_row(
                event_type=event_type,
                cam_id=cam_id,
                ts=ts,
                detected_at=detected_at,
                payload=payload,
                manifest_payload=entry,
                json_file_path=json_remote or None,
                video_url=video_url,
                crop_url=None,
                image_url=None,
                track_id=track_id,
            )

        # Evento con JSON de detalle (plate, person)
        json_remote = str(entry.get("file") or "")
        if not json_remote:
            return None

        try:
            data = self._ssh.read_file_bytes(json_remote)
            payload = json.loads(data)
        except Exception as exc:
            logger.debug("[MediaIngest] No se pudo leer %s: %s", json_remote, exc)
            return None

        crop_remote = str(payload.get("crop_path") or "")
        crop_url = self._upload_remote(crop_remote, event_type, cam_id) if crop_remote else None

        return self._build_row(
            event_type=event_type,
            cam_id=cam_id,
            ts=ts,
            detected_at=detected_at,
            payload=payload,
            manifest_payload=entry,
            json_file_path=json_remote,
            video_url=None,
            crop_url=crop_url,
            image_url=None,
            track_id=None,
        )

    def _upload_remote(self, remote_path: str, event_type: str, cam_id: str) -> str | None:
        if not remote_path:
            return None
        filename = PurePosixPath(remote_path).name
        key = _object_key(event_type, cam_id, filename)

        if self._minio.object_exists(key):
            return _public_url(
                self._s.minio_public_endpoint,
                self._s.minio_bucket,
                key,
                self._s.minio_secure,
            )

        try:
            data = self._ssh.read_file_bytes(remote_path)
        except Exception as exc:
            logger.warning("[MediaIngest] SFTP read falló %s: %s", remote_path, exc)
            return None

        try:
            url = self._minio.upload_bytes(data, key)
            logger.debug("[MediaIngest] Subido → %s", url)
            return url
        except Exception as exc:
            logger.warning("[MediaIngest] MinIO upload falló %s: %s", key, exc)
            return None

    @staticmethod
    def _build_row(
        *,
        event_type: str,
        cam_id: str,
        ts: int,
        detected_at: datetime,
        payload: dict,
        manifest_payload: dict,
        json_file_path: str | None,
        video_url: str | None,
        crop_url: str | None,
        image_url: str | None,
        track_id: int | None,
    ) -> tuple:
        plate = str(payload.get("plate") or "").strip() or None
        person_id = str(payload.get("person_id") or "").strip() or None
        person_name = str(payload.get("person_name") or "").strip() or None

        return (
            event_type,
            _event_category(event_type),
            "fixed_camera",
            cam_id,
            cam_id,                         # camera_name (igual a cam_id si no hay lookup)
            ts or None,
            detected_at,
            detected_at.date(),
            _event_title(event_type),
            None,                            # description
            person_id,
            person_name,
            plate,
            track_id,
            "new",
            _event_severity(event_type),
            None,                            # manifest_file_path
            json_file_path,
            video_url,
            image_url,
            crop_url,
            Json(manifest_payload),
            Json(payload),
        )

    def _insert_rows(self, rows: list[tuple]) -> None:
        # Deduplicar por event_uid (mismo hash que la tabla)
        unique: dict[str, tuple] = {}
        for row in rows:
            uid = _compute_uid(row)
            unique[uid] = row

        query = """
            INSERT INTO camera_event_history (
                event_type, event_category, origin, camera_id, camera_name,
                event_timestamp, detected_at, detected_date,
                title, description, person_id, person_name, plate, track_id,
                status, severity,
                manifest_file_path, json_file_path, video_file_path,
                image_file_path, crop_path,
                manifest_payload, detail_payload
            ) VALUES %s
            ON CONFLICT ON CONSTRAINT uq_camera_event_history_event_uid DO UPDATE SET
                video_file_path  = COALESCE(EXCLUDED.video_file_path,  camera_event_history.video_file_path),
                crop_path        = COALESCE(EXCLUDED.crop_path,        camera_event_history.crop_path),
                image_file_path  = COALESCE(EXCLUDED.image_file_path,  camera_event_history.image_file_path),
                detail_payload   = EXCLUDED.detail_payload,
                updated_at       = now()
        """
        dsn = _psycopg_dsn(self._s.database_url)
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, list(unique.values()))
            conn.commit()


def _compute_uid(row: tuple) -> str:
    # Mismo cálculo que la columna generada en PostgreSQL
    # event_type=0, cam_id=3, ts=5, track_id=13, person_id=10, plate=12,
    # json_file_path=17, video_url=18, image_url=19, crop_url=20, manifest=16
    fields = (row[3], row[0], row[5], row[13], row[10], row[12],
              row[17], row[18], row[19], row[20], row[16])
    raw = "|".join("" if v is None else str(v) for v in fields)
    return hashlib.md5(raw.encode()).hexdigest()


def _psycopg_dsn(url: str) -> str:
    from urllib.parse import urlparse, urlunparse, unquote
    p = urlparse(url)
    return urlunparse(p)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    settings = get_settings()
    service = MediaIngestService(settings)
    service.run_forever(poll_interval=4.0)


if __name__ == "__main__":
    main()
