from __future__ import annotations

import mimetypes
import re
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from secrets import compare_digest
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Request, UploadFile
from minio import Minio
from minio.error import S3Error
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(prefix="/ingest", tags=["ingest"])

VIDEO_EVENT_TYPES = {"clip", "clips_zona", "clips_movimiento", "click"}
ALLOWED_ORIGINS = {"fixed_camera", "vehicle", "drone", "system"}
ALLOWED_STATUSES = {"new", "reviewed", "archived", "dismissed"}
ALLOWED_SEVERITIES = {"info", "warning", "critical"}


def _require_ingest_token(
    request: Request,
    x_robiotec_ingest_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.service_ingest_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="ingest_disabled")

    supplied = (x_robiotec_ingest_token or "").strip()
    auth = request.headers.get("Authorization", "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_ingest_token")


def _event_category(event_type: str) -> str:
    return {"plate": "vehiculo", "person": "reconocimiento_facial"}.get(event_type, "movimiento")


def _event_title(event_type: str) -> str:
    return {
        "plate": "Vehiculo detectado",
        "person": "Persona detectada",
        "clip": "Video de zona detectado",
        "clips_zona": "Zona activa detectada",
        "clips_movimiento": "Movimiento detectado",
    }.get(event_type, "Evento detectado")


def _event_severity(event_type: str) -> str:
    return "warning" if event_type in VIDEO_EVENT_TYPES else "info"


def _text_value(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _int_value(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
    else:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: Any, fallback: datetime) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    return fallback.date()


def _safe_object_part(value: str, default: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned[:160] or default


def _object_prefix(event_type: str) -> str:
    if event_type in VIDEO_EVENT_TYPES:
        return "clips"
    if event_type == "plate":
        return "plates"
    if event_type == "person":
        return "persons"
    return "misc"


def _public_minio_url(settings: Settings, key: str) -> str:
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_public_endpoint}/{settings.minio_bucket}/{key}"


_minio_client: Minio | None = None


def _get_minio(settings: Settings) -> Minio:
    global _minio_client
    if _minio_client is None:
        if not settings.minio_access_key or not settings.minio_secret_key:
            raise HTTPException(status_code=503, detail="minio_not_configured")
        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _minio_client


def _ensure_bucket(client: Minio, bucket: str) -> None:
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error as exc:
        raise HTTPException(status_code=503, detail=f"minio_bucket_error:{exc.code}") from exc


@router.post("/media", dependencies=[Depends(_require_ingest_token)])
async def upload_media(
    file: UploadFile = File(...),
    camera_id: str = Form(default="unknown"),
    event_type: str = Form(default="misc"),
    filename: str = Form(default=""),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    event_type = _safe_object_part(event_type.lower(), "misc")
    camera_id = _safe_object_part(camera_id, "unknown")
    original_name = PurePosixPath(filename or file.filename or "").name
    object_name = _safe_object_part(original_name, f"{uuid4().hex}.bin")
    key = f"{_object_prefix(event_type)}/{camera_id}/{object_name}"

    client = _get_minio(settings)
    _ensure_bucket(client, settings.minio_bucket)

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    content_type = file.content_type or mimetypes.guess_type(object_name)[0] or "application/octet-stream"
    try:
        client.put_object(settings.minio_bucket, key, file.file, size, content_type=content_type)
    except S3Error as exc:
        raise HTTPException(status_code=503, detail=f"minio_upload_error:{exc.code}") from exc

    return {
        "ok": True,
        "bucket": settings.minio_bucket,
        "object_key": key,
        "url": _public_minio_url(settings, key),
        "size": size,
        "content_type": content_type,
    }


def _event_row(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("event_type") or payload.get("type") or "").strip().lower()
    camera_id = str(payload.get("camera_id") or payload.get("cam_id") or "").strip()
    if not event_type or not camera_id:
        raise HTTPException(status_code=400, detail="event_type_and_camera_id_required")

    detected_at = _parse_datetime(payload.get("detected_at") or payload.get("timestamp"))
    status = str(payload.get("status") or "new").strip().lower()
    severity = str(payload.get("severity") or _event_severity(event_type)).strip().lower()
    origin = str(payload.get("origin") or "fixed_camera").strip().lower()
    if status not in ALLOWED_STATUSES:
        status = "new"
    if severity not in ALLOWED_SEVERITIES:
        severity = _event_severity(event_type)
    if origin not in ALLOWED_ORIGINS:
        origin = "fixed_camera"

    detail_payload = payload.get("detail_payload")
    if not isinstance(detail_payload, dict):
        detail_payload = {}
    manifest_payload = payload.get("manifest_payload")
    if not isinstance(manifest_payload, dict):
        manifest_payload = {}

    return {
        "event_type": event_type,
        "event_category": _text_value(payload.get("event_category")) or _event_category(event_type),
        "origin": origin,
        "camera_id": camera_id,
        "camera_name": _text_value(payload.get("camera_name")) or camera_id,
        "camera_location": _text_value(payload.get("camera_location")),
        "event_timestamp": _int_value(payload.get("event_timestamp")),
        "detected_at": detected_at,
        "detected_date": _parse_date(payload.get("detected_date"), detected_at),
        "title": _text_value(payload.get("title")) or _event_title(event_type),
        "description": _text_value(payload.get("description")),
        "person_id": _text_value(payload.get("person_id")),
        "person_name": _text_value(payload.get("person_name")),
        "plate": _text_value(payload.get("plate")),
        "track_id": _int_value(payload.get("track_id")),
        "status": status,
        "severity": severity,
        "manifest_file_path": _text_value(payload.get("manifest_file_path")),
        "json_file_path": _text_value(payload.get("json_file_path")),
        "video_file_path": _text_value(payload.get("video_file_path")),
        "image_file_path": _text_value(payload.get("image_file_path")),
        "crop_path": _text_value(payload.get("crop_path")),
        "manifest_payload": manifest_payload,
        "detail_payload": detail_payload,
    }


_UPSERT_EVENT_SQL = text(
    """
    INSERT INTO camera_event_history (
        event_type, event_category, origin, camera_id, camera_name, camera_location,
        event_timestamp, detected_at, detected_date,
        title, description, person_id, person_name, plate, track_id,
        status, severity,
        manifest_file_path, json_file_path, video_file_path, image_file_path, crop_path,
        manifest_payload, detail_payload
    ) VALUES (
        :event_type, :event_category, :origin, :camera_id, :camera_name, :camera_location,
        :event_timestamp, :detected_at, :detected_date,
        :title, :description, :person_id, :person_name, :plate, :track_id,
        :status, :severity,
        :manifest_file_path, :json_file_path, :video_file_path, :image_file_path, :crop_path,
        :manifest_payload, :detail_payload
    )
    ON CONFLICT ON CONSTRAINT uq_camera_event_history_event_uid DO UPDATE SET
        camera_name = COALESCE(EXCLUDED.camera_name, camera_event_history.camera_name),
        camera_location = COALESCE(EXCLUDED.camera_location, camera_event_history.camera_location),
        video_file_path = COALESCE(EXCLUDED.video_file_path, camera_event_history.video_file_path),
        image_file_path = COALESCE(EXCLUDED.image_file_path, camera_event_history.image_file_path),
        crop_path = COALESCE(EXCLUDED.crop_path, camera_event_history.crop_path),
        manifest_payload = EXCLUDED.manifest_payload,
        detail_payload = EXCLUDED.detail_payload,
        updated_at = now()
    RETURNING id, event_uid
    """
).bindparams(
    bindparam("manifest_payload", type_=JSONB),
    bindparam("detail_payload", type_=JSONB),
)


def _insert_event(db: Session, row: dict[str, Any]) -> dict[str, Any]:
    result = db.execute(_UPSERT_EVENT_SQL, row).mappings().first()
    if result is None:
        raise HTTPException(status_code=500, detail="event_not_saved")
    return {"id": str(result["id"]), "event_uid": result["event_uid"]}


@router.post("/camera-events", dependencies=[Depends(_require_ingest_token)])
async def create_camera_event(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    saved = _insert_event(db, _event_row(payload))
    db.commit()
    return {"ok": True, **saved}


@router.post("/camera-events/batch", dependencies=[Depends(_require_ingest_token)])
async def create_camera_events_batch(payload: Any = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items_required")
    if len(items) > 500:
        raise HTTPException(status_code=413, detail="too_many_items")
    saved: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="invalid_item")
        saved.append(_insert_event(db, _event_row(item)))
    db.commit()
    return {"ok": True, "count": len(saved), "items": saved}
