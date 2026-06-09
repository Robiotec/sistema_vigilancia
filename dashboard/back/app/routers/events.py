"""Router de historial de eventos y archivos multimedia de eventos."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from back.app.context import _text, get_token
from back.app.state import remote_detection_feed

router = APIRouter(prefix="/api", tags=["events"])


def _camera_lookup_from_request(request: Request, *, camera: str = "", camera_name: str = ""):
    from back.app.routers.cameras import _camera_lookup
    return _camera_lookup(request, camera=camera, camera_name=camera_name)


@router.get("/camera-events")
def camera_events(request: Request, camera: str = "", camera_name: str = "", limit: int = 8):
    item = _camera_lookup_from_request(request, camera=camera, camera_name=camera_name)
    cam_id = _text(item.get("codigo_unico") or item.get("path") or item.get("name")) if item else _text(camera_name or camera)
    if not cam_id:
        return JSONResponse([], status_code=200)
    try:
        return JSONResponse(remote_detection_feed.fetch_camera_events(cam_id, limit=limit))
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": []}, status_code=503)


@router.get("/event-history")
def event_history(
    page: int = 1,
    page_size: int = 8,
    q: str = "",
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
):
    try:
        return JSONResponse(
            remote_detection_feed.fetch_event_history(
                page=page,
                page_size=page_size,
                query=q,
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
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": [], "total": 0}, status_code=503)


@router.get("/event-history-filter-options")
def event_history_filter_options(field: str = ""):
    try:
        return JSONResponse(remote_detection_feed.fetch_event_history_filter_options(field))
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": [], "total": 0}, status_code=400)


@router.patch("/event-history/{event_id}/status")
async def event_history_status(event_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        return JSONResponse(remote_detection_feed.update_event_history_status(event_id, _text(payload.get("status"))))
    except FileNotFoundError:
        return JSONResponse({"error": "Evento no encontrado"}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/camera-event-crop")
def camera_event_crop(path: str):
    try:
        content, media_type = remote_detection_feed.read_remote_file(path)
    except FileNotFoundError:
        return Response(status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "public, max-age=300"})


@router.get("/camera-event-video")
def camera_event_video(path: str):
    try:
        local_path, media_type = remote_detection_feed.cache_remote_video(path)
    except FileNotFoundError:
        return Response(status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return FileResponse(local_path, media_type=media_type)


@router.get("/events")
def events():
    return []


@router.get("/evidence")
def evidence():
    return []
