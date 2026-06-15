#!/usr/bin/env python3
"""Worker remoto: vigila manifest.jsonl y publica eventos via API Central."""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

ECUADOR_TZ = timezone(timedelta(hours=-5))
VIDEO_EVENT_TYPES = {"clip", "clips_zona", "clips_movimiento", "click"}


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


MANIFEST_PATH = Path(_env("AI_RESULTS_DIR", "/home/robiotec/robiotec-ai/results")) / "manifest.jsonl"
STATE_FILE = Path(_env("INGEST_STATE_FILE", "/home/robiotec/robiotec-ai/data/manifest_ingest_state.json"))
POLL_INTERVAL = float(_env("INGEST_POLL_INTERVAL", "4"))

API_INGEST_BASE = _env("API_INGEST_BASE", "https://robio-ai.com/api/ingest").rstrip("/")
API_INGEST_TOKEN = _env("API_INGEST_TOKEN") or _env("SERVICE_INGEST_TOKEN")
API_VERIFY_TLS = _env("API_VERIFY_TLS", "true").lower() not in {"0", "false", "no"}
API_CONNECT_TIMEOUT = float(_env("API_CONNECT_TIMEOUT", "10"))
API_READ_TIMEOUT = float(_env("API_READ_TIMEOUT", "180"))

_session = requests.Session()


def _headers() -> dict[str, str]:
    if not API_INGEST_TOKEN:
        raise RuntimeError("Falta API_INGEST_TOKEN para publicar eventos")
    return {"X-Robiotec-Ingest-Token": API_INGEST_TOKEN}


def _api_post_json(path: str, payload: Any) -> dict[str, Any]:
    url = f"{API_INGEST_BASE}/{path.lstrip('/')}"
    response = _session.post(
        url,
        json=payload,
        headers=_headers(),
        timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT),
        verify=API_VERIFY_TLS,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Respuesta API no exitosa: {data}")
    return data


def _api_upload_file(local_path: Path, event_type: str, cam_id: str) -> str:
    url = f"{API_INGEST_BASE}/media"
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    with local_path.open("rb") as fh:
        response = _session.post(
            url,
            data={"camera_id": cam_id, "event_type": event_type, "filename": local_path.name},
            files={"file": (local_path.name, fh, content_type)},
            headers=_headers(),
            timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT),
            verify=API_VERIFY_TLS,
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok") or not data.get("url"):
        raise RuntimeError(f"Upload API no exitoso: {data}")
    return str(data["url"])


def _int_val(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


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


def _upload_file(local_path: str, event_type: str, cam_id: str) -> str | None:
    if not local_path:
        return None
    path = Path(local_path)
    if not path.exists():
        logger.debug("[ingest] Archivo no encontrado: %s", local_path)
        return None
    url = _api_upload_file(path, event_type, cam_id)
    logger.debug("[ingest] Subido por API: %s", url)
    return url


def _load_state() -> dict[str, Any]:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"offset": 0, "processed": 0}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state))


def _compute_uid(row: dict[str, Any]) -> str:
    fields = (
        row["camera_id"],
        row["event_type"],
        row.get("event_timestamp"),
        row.get("track_id"),
        row.get("person_id"),
        row.get("plate"),
        row.get("json_file_path"),
        row.get("video_file_path"),
        row.get("image_file_path"),
        row.get("crop_path"),
        row.get("manifest_file_path"),
    )
    return hashlib.md5("|".join("" if value is None else str(value) for value in fields).encode()).hexdigest()


def _insert_rows(rows: list[dict[str, Any]]) -> None:
    unique = list({_compute_uid(row): row for row in rows}.values())
    if not unique:
        return
    if len(unique) == 1:
        _api_post_json("camera-events", unique[0])
    else:
        _api_post_json("camera-events/batch", {"items": unique})
    logger.info("[ingest] %d evento(s) enviados por API.", len(unique))


def _build_row(
    *,
    event_type: str,
    cam_id: str,
    ts: int,
    detected_at: datetime,
    payload: dict[str, Any],
    entry: dict[str, Any],
    json_file_path: str | None,
    video_url: str | None,
    crop_url: str | None,
    track_id: int | None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "event_category": _event_category(event_type),
        "origin": "fixed_camera",
        "camera_id": cam_id,
        "camera_name": cam_id,
        "event_timestamp": ts or None,
        "detected_at": detected_at.isoformat(),
        "detected_date": detected_at.date().isoformat(),
        "title": _event_title(event_type),
        "description": None,
        "person_id": str(payload.get("person_id") or "").strip() or None,
        "person_name": str(payload.get("person_name") or "").strip() or None,
        "plate": str(payload.get("plate") or "").strip() or None,
        "track_id": track_id,
        "status": "new",
        "severity": _event_severity(event_type),
        "manifest_file_path": None,
        "json_file_path": json_file_path,
        "video_file_path": video_url,
        "image_file_path": None,
        "crop_path": crop_url,
        "manifest_payload": entry,
        "detail_payload": payload,
    }


def _process_line(line: str) -> dict[str, Any] | None:
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

    if event_type in VIDEO_EVENT_TYPES:
        clip_remote = str(entry.get("clip_file") or entry.get("file") or "")
        json_remote = str(entry.get("json_file") or "")
        payload: dict[str, Any] = dict(entry)
        if json_remote:
            try:
                loaded = json.loads(Path(json_remote).read_text())
                if isinstance(loaded, dict):
                    payload.update(loaded)
            except Exception:
                pass
        video_url = _upload_file(clip_remote, event_type, cam_id)
        track_id = _int_val(payload.get("track_id") or entry.get("track_id"))
        return _build_row(
            event_type=event_type,
            cam_id=cam_id,
            ts=ts,
            detected_at=detected_at,
            payload=payload,
            entry=entry,
            json_file_path=json_remote or None,
            video_url=video_url,
            crop_url=None,
            track_id=track_id,
        )

    json_remote = str(entry.get("file") or "")
    if not json_remote:
        return None
    try:
        payload = json.loads(Path(json_remote).read_text())
    except Exception as exc:
        logger.debug("[ingest] No se pudo leer %s: %s", json_remote, exc)
        return None
    crop_url = _upload_file(str(payload.get("crop_path") or ""), event_type, cam_id)
    return _build_row(
        event_type=event_type,
        cam_id=cam_id,
        ts=ts,
        detected_at=detected_at,
        payload=payload,
        entry=entry,
        json_file_path=json_remote,
        video_url=None,
        crop_url=crop_url,
        track_id=None,
    )


def tick() -> int:
    state = _load_state()
    if not MANIFEST_PATH.exists():
        return 0

    size = MANIFEST_PATH.stat().st_size
    offset = state.get("offset", 0)
    if size <= offset:
        return 0

    with MANIFEST_PATH.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read(size - offset)

    lines = [line for line in chunk.decode("utf-8", errors="replace").splitlines() if line.strip()]
    new_offset = offset + len(chunk)
    rows = [row for line in lines for row in [_process_line(line)] if row]
    if rows:
        _insert_rows(rows)

    state["offset"] = new_offset
    state["processed"] = state.get("processed", 0) + len(rows)
    _save_state(state)
    return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    logger.info("[ingest] Iniciando via API - manifest: %s", MANIFEST_PATH)
    while True:
        try:
            count = tick()
            if count:
                logger.info("[ingest] %d evento(s) nuevos procesados.", count)
        except KeyboardInterrupt:
            logger.info("[ingest] Detenido.")
            break
        except Exception as exc:
            logger.error("[ingest] Error en ciclo: %s", exc, exc_info=True)
            time.sleep(10)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
