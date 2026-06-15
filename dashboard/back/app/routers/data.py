"""Router de datos geoespaciales: ARCOM, OSINT, tracks de drones y objetivos."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from back.app.context import _text, call_api, get_token, require_authenticated_request

router = APIRouter(prefix="/api", tags=["data"], dependencies=[Depends(require_authenticated_request)])

_DRONE_TRACKS: dict[str, dict[str, Any]] = {}
_DRONE_TRACKS_LOCK = threading.Lock()
_MAX_TRACK_FLIGHTS_PER_DEVICE = 24
_MAX_TRACK_POINTS_PER_FLIGHT = 2000
_OBJECTIVE_CLEARED_AFTER: dict[str, float] = {}
_OBJECTIVE_LOCK = threading.Lock()


@router.get("/arcom/concessions")
def arcom_concessions(bbox: str = "", limit: int = 120):
    try:
        return call_api(f"/arcom/concessions?bbox={quote(bbox)}&limit={int(limit or 120)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@router.get("/arcom/concession-lookup")
def arcom_concession_lookup(lat: float, lon: float):
    try:
        return call_api(f"/arcom/concession-lookup?lat={lat}&lon={lon}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "found": False, "concession": None}, status_code=503)


@router.get("/osint/layers")
def osint_layers(bbox: str = "", limit: int = 2000, layer: str = ""):
    try:
        return call_api(f"/osint/layers?bbox={quote(bbox)}&limit={int(limit or 2000)}&layer={quote(layer)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@router.get("/osint/report")
def osint_report():
    try:
        return call_api("/osint/report")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "available": False}, status_code=503)


def _point_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    point = payload.get("point") if isinstance(payload.get("point"), dict) else None
    if not point:
        return None
    try:
        lat = float(point.get("lat"))
        lon = float(point.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    normalized = {
        "lat": lat,
        "lon": lon,
        "altitude": point.get("altitude"),
        "speed": point.get("speed"),
        "heading": point.get("heading"),
        "ts": point.get("ts") or payload.get("ts") or int(time.time() * 1000),
    }
    return normalized


def _public_drone_tracks() -> dict[str, Any]:
    tracks = []
    with _DRONE_TRACKS_LOCK:
        for device_id, track in _DRONE_TRACKS.items():
            flights = list(track.get("flights") or [])
            active = track.get("active")
            if active and active.get("points"):
                flights.append(active)
            tracks.append(
                {
                    "device_id": device_id,
                    "label": track.get("label") or device_id,
                    "flights": flights[-_MAX_TRACK_FLIGHTS_PER_DEVICE:],
                }
            )
    return {"ok": True, "tracks": tracks, "total": len(tracks)}


@router.get("/tracks/drone")
def drone_tracks():
    return _public_drone_tracks()


@router.post("/tracks/drone/{device_id}/point")
async def drone_track_point(device_id: str, request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        payload = {}
    normalized_id = _text(device_id)
    if not normalized_id:
        return JSONResponse({"ok": False, "error": "device_id_required"}, status_code=400)

    state = _text(payload.get("state")).lower() or "armed"
    label = _text(payload.get("label")) or normalized_id
    ts = payload.get("ts") or int(time.time() * 1000)
    started_at = payload.get("started_at") or ts
    point = _point_from_payload(payload)

    with _DRONE_TRACKS_LOCK:
        track = _DRONE_TRACKS.setdefault(
            normalized_id,
            {"device_id": normalized_id, "label": label, "active": None, "flights": []},
        )
        track["label"] = label
        active = track.get("active")
        if not active and state != "disarmed":
            active = {
                "device_id": normalized_id,
                "label": label,
                "kind": "drone",
                "state": "armed",
                "started_at": started_at,
                "ended_at": None,
                "points": [],
            }
            track["active"] = active
        if active and point:
            points = active.setdefault("points", [])
            if not points or points[-1].get("lat") != point["lat"] or points[-1].get("lon") != point["lon"]:
                points.append(point)
                del points[:-_MAX_TRACK_POINTS_PER_FLIGHT]
        if state == "disarmed" and active:
            active["state"] = "disarmed"
            active["ended_at"] = ts
            if len(active.get("points") or []) >= 2:
                flights = track.setdefault("flights", [])
                flights.append(active)
                del flights[:-_MAX_TRACK_FLIGHTS_PER_DEVICE]
            track["active"] = None
    return {"ok": True, **_public_drone_tracks()}


@router.post("/tracks/drone/clear")
def drone_tracks_clear():
    with _DRONE_TRACKS_LOCK:
        _DRONE_TRACKS.clear()
    return {"ok": True}


@router.get("/aircraft/viewport")
def aircraft_viewport(bbox: str = ""):
    return {"ok": True, "bbox": _text(bbox), "aircraft": [], "source": "not_configured"}


def _timestamp_ms(value: Any) -> float:
    if value is None:
        return time.time() * 1000
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric > 99999999999 else numeric * 1000
    raw = _text(value)
    if not raw:
        return time.time() * 1000
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp() * 1000
    except ValueError:
        return time.time() * 1000


def _iso_from_timestamp_ms(ts_ms: float) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _objective_data_from_telemetry(objective_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    ts_ms = _timestamp_ms(
        item.get("received_at")
        or item.get("timestamp")
        or extra.get("gps_datetime_iso")
        or extra.get("gps_datetime")
        or extra.get("last_update_ts")
    )
    with _OBJECTIVE_LOCK:
        cleared_after = _OBJECTIVE_CLEARED_AFTER.get(objective_id.upper(), 0)
    if ts_ms <= cleared_after:
        return None

    device_id = _text(item.get("device_id") or extra.get("api_device_id") or extra.get("gps_api_id"))
    source_id = _text(item.get("vehicle_source_id") or extra.get("vehicle_source_id"))
    label = _text(item.get("display_name") or item.get("camera_name") or device_id or source_id or objective_id)
    data = {
        "id": f"{objective_id.upper()}:{source_id or device_id or label}",
        "objective_id": objective_id.upper(),
        "label": label,
        "device_id": device_id,
        "vehicle_source_id": source_id,
        "latitud": lat,
        "longitud": lon,
        "updated_at": _iso_from_timestamp_ms(ts_ms),
        "speed": item.get("speed"),
        "heading": item.get("heading"),
        "freshness": item.get("freshness"),
    }
    payload = {"found": True, "data": data}
    try:
        concession = call_api(f"/arcom/concession-lookup?lat={lat}&lon={lon}")
    except RuntimeError:
        concession = None
    if isinstance(concession, dict) and concession.get("found") and isinstance(concession.get("concession"), dict):
        payload["concession"] = concession["concession"]
    return payload


@router.get("/objetivos/{objective_id}")
def high_value_objective(objective_id: str, request: Request):
    normalized_id = _text(objective_id).upper()
    if not normalized_id:
        return JSONResponse({"ok": False, "error": "objective_id_required"}, status_code=400)

    token = get_token(request)
    try:
        telemetry = call_api("/telemetry/latest", token=token) or []
    except RuntimeError as exc:
        return JSONResponse({"id": normalized_id, "found": False, "points": [], "error": str(exc)}, status_code=503)

    points: list[dict[str, Any]] = []
    for item in telemetry if isinstance(telemetry, list) else []:
        if not isinstance(item, dict):
            continue
        marker_type = _text(item.get("vehicle_type") or item.get("vehicle_type_code") or item.get("device_kind")).lower()
        if normalized_id == "DRONE" and "dron" not in marker_type and "drone" not in marker_type:
            continue
        point = _objective_data_from_telemetry(normalized_id, item)
        if point:
            points.append(point)

    return {
        "id": normalized_id,
        "found": bool(points),
        "points": points,
        "data": points[0]["data"] if points else None,
    }


@router.post("/objetivos/{objective_id}/clear")
def high_value_objective_clear(objective_id: str):
    normalized_id = _text(objective_id).upper()
    if not normalized_id:
        return JSONResponse({"ok": False, "error": "objective_id_required"}, status_code=400)
    with _OBJECTIVE_LOCK:
        _OBJECTIVE_CLEARED_AFTER[normalized_id] = time.time() * 1000
    return {"id": normalized_id, "ok": True, "cleared_after": _iso_from_timestamp_ms(_OBJECTIVE_CLEARED_AFTER[normalized_id])}
