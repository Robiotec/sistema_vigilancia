from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
from typing import Any

from back.app.config import get_settings
from back.app.services.remote_detection_feed import RemoteDetectionFeedService, VIDEO_EVENT_TYPES


def ingest_manifest_events(
    service: RemoteDetectionFeedService,
    *,
    limit_per_camera: int,
    tail_mb: int,
) -> dict[str, Any]:
    video_types_repr = repr(tuple(VIDEO_EVENT_TYPES))
    base_path_repr = repr(service.settings.ssh_events_base_path)

    remote_python = f"""
import json
from pathlib import Path

base = Path({base_path_repr})
manifest = base / "manifest.jsonl"

limit_per_camera = {max(1, int(limit_per_camera))}
VIDEO_TYPES = {video_types_repr}
TAIL_BYTES = {max(1, int(tail_mb))} * 1024 * 1024

items = []
per_camera = {{}}


def resolve_path(value, cam_id=""):
    raw = str(value or "").strip()
    if not raw:
        return None

    path = Path(raw)

    if path.is_absolute():
        return path

    parts = path.parts

    # Si el manifest guarda rutas tipo:
    # results_presentacion/CAM-X/evento.json
    # y base ya es results_presentacion, se quita el segmento duplicado.
    if parts and parts[0] == base.name:
        path = Path(*parts[1:]) if len(parts) > 1 else Path(".")

    candidates = []

    if cam_id:
        candidates.append(base / cam_id / path)

    candidates.append(base / path)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1] if candidates else base / path


def read_tail_lines(path, tail_bytes):
    size = path.stat().st_size
    offset = max(0, size - tail_bytes)

    with path.open("rb") as fh:
        fh.seek(offset)
        raw = fh.read()

    text = raw.decode("utf-8", errors="replace")

    if offset > 0:
        nl = text.find("\\n")
        text = text[nl + 1:] if nl >= 0 else ""

    return text.splitlines()


if manifest.exists():
    # IMPORTANTE:
    # Se lee de abajo hacia arriba para tomar primero los eventos más recientes.
    # Antes se leía de arriba hacia abajo y el límite por cámara podía llenarse
    # con eventos antiguos, dejando fuera los últimos eventos del manifest.
    for line in reversed(read_tail_lines(manifest, TAIL_BYTES)):
        line = line.strip()

        if not line:
            continue

        try:
            row = json.loads(line)
        except Exception:
            continue

        cam_id = str(row.get("cam_id") or "").strip()

        # Única condición obligatoria:
        # si el evento no tiene cam_id, no se guarda.
        if not cam_id:
            continue

        if per_camera.get(cam_id, 0) >= limit_per_camera:
            continue

        event_type = str(row.get("type") or "").strip()

        if not event_type:
            continue

        if event_type in VIDEO_TYPES:
            video_file = resolve_path(row.get("clip_file") or row.get("file"), cam_id)
            json_file = resolve_path(row.get("json_file"), cam_id)

            if not video_file:
                continue

            payload = dict(row)

            if json_file and json_file.exists():
                try:
                    loaded_payload = json.loads(
                        json_file.read_text(encoding="utf-8", errors="replace")
                    )
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
                "crop_path": str(payload.get("crop_path") or ""),
                "video_path": str(video_file),
                "manifest_payload": row,
                "payload": payload,
            }})

            per_camera[cam_id] = per_camera.get(cam_id, 0) + 1
            continue

        source_file = resolve_path(row.get("file"), cam_id)

        if not source_file or not source_file.exists():
            continue

        try:
            payload = json.loads(source_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue

        items.append({{
            "event_type": event_type,
            "cam_id": cam_id,
            "timestamp": int(row.get("ts") or payload.get("timestamp") or 0),
            "source_file": str(source_file),
            "crop_path": str(payload.get("crop_path") or ""),
            "video_path": "",
            "manifest_payload": row,
            "payload": payload,
        }})

        per_camera[cam_id] = per_camera.get(cam_id, 0) + 1


# Se ordena por timestamp ascendente antes de persistir.
# No es obligatorio, pero deja una inserción más ordenada.
items.sort(key=lambda item: int(item.get("timestamp") or 0))

print(json.dumps({{
    "items": items,
    "per_camera": per_camera,
    "manifest_exists": manifest.exists(),
    "manifest_path": str(manifest),
}}, ensure_ascii=False))
"""

    output = service._run_python(remote_python)
    parsed = json.loads(output or "{}")

    items = parsed.get("items") if isinstance(parsed.get("items"), list) else []

    service._persist_events(items)

    return {
        "items": len(items),
        "per_camera": parsed.get("per_camera") or {},
        "manifest_exists": parsed.get("manifest_exists"),
        "manifest_path": parsed.get("manifest_path"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingesta eventos remotos desde manifest.jsonl sin depender de cámaras activas."
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--tail-mb", type=int, default=20)
    args = parser.parse_args()

    settings = get_settings()

    data_dir = Path(__file__).resolve().parents[1] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    lock_path = data_dir / "remote_event_ingest.lock"

    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"skipped": "already_running"}, ensure_ascii=False))
            return 0

        service = RemoteDetectionFeedService(settings)

        result: dict[str, Any] = {
            "mode": "manifest_all_camera_ids",
            "depends_on_active_cameras": False,
        }

        result.update(
            ingest_manifest_events(
                service,
                limit_per_camera=args.limit,
                tail_mb=args.tail_mb,
            )
        )

        print(json.dumps(result, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())