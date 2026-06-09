"""
Router de cámaras, RBoxes, inferencia, visor y snapshots.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from back.app.context import (
    _text,
    _json,
    _num_id,
    auth_json_response,
    api_error_response,
    build_context,
    call_api,
    clear_context_cache,
    companies_for_options,
    db_camera_items,
    ensure_company,
    fetch_db_camera_names,
    fetch_db_camera_rows,
    fetch_db_camera_unique_codes,
    get_token,
    normalize_camera_item,
    normalize_drone_item,
    normalize_vehicle_item,
    resolve_source_id,
    camera_unique_code_options_html,
)
from back.app.state import (
    camera_form_mapper,
    camera_normalizer,
    device_catalog,
    drone_normalizer,
    empresa_mapper,
    remote_detection_feed,
    rbox_mapper,
    settings,
    stream_config_mapper,
    vehicle_normalizer,
)

router = APIRouter(prefix="/api", tags=["cameras"])

# ---------------------------------------------------------------------------
# Constantes de inferencia
# ---------------------------------------------------------------------------

CAMERA_INFERENCE_TYPE_BY_UI = {
    "none": "inactiva",
    "plates": "placa",
    "faces": "rostro",
    "access": "zona",
    "hands_helmet": "movimiento",
}
CAMERA_DB_INFERENCE_TYPES = set(CAMERA_INFERENCE_TYPE_BY_UI.values())
CAMERA_UI_INFERENCE_TYPE_BY_DB = {
    "inactiva": "none",
    "placa": "plates",
    "placas": "plates",
    "rostro": "faces",
    "rostros": "faces",
    "zona": "access",
    "zonas": "access",
    "movimiento": "hands_helmet",
    "movimientos": "hands_helmet",
}
INFERENCE_SUFFIX = "/INFERENCE"
_INFERENCE_VIEW_TTL_SECONDS = 20
_INFERENCE_VIEW_SCHEMA_READY = False
_INFERENCE_VIEW_SCHEMA_LOCK = threading.Lock()

_CAMERA_NOTIF_SCHEMA_READY = False
_CAMERA_NOTIF_SCHEMA_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Caché de snapshots y mapa de paths de cámaras
# ---------------------------------------------------------------------------

_SNAPSHOT_STORE: dict[str, tuple[bytes, float]] = {}
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_REFRESHING: set[str] = set()
_SNAPSHOT_TTL = 180.0
_SNAPSHOT_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cam-snap")

_CAM_PATH_MAP: dict[str, str] = {}
_CAM_PATH_LOCK = threading.Lock()

_SNAPSHOT_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90">'
    '<rect width="160" height="90" fill="#0a0c14"/>'
    '<rect x="1" y="1" width="158" height="88" rx="6" fill="none" stroke="rgba(255,255,255,.08)"/>'
    '<g transform="translate(80,38)" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="1.5">'
    '<rect x="-14" y="-10" width="28" height="20" rx="3"/>'
    '<rect x="14" y="-4" width="6" height="8" rx="2"/>'
    '<circle cx="0" cy="0" r="5"/>'
    '</g>'
    '<text x="80" y="65" text-anchor="middle" font-family="system-ui,sans-serif" '
    'font-size="7" fill="rgba(255,255,255,.32)" font-weight="700" letter-spacing="1">SIN SEÑAL</text>'
    '</svg>'
).encode()


# ---------------------------------------------------------------------------
# Startup helper (llamado desde application.py)
# ---------------------------------------------------------------------------

def start_cam_path_map_refresher() -> None:
    threading.Thread(target=_cam_path_map_refresh_loop, daemon=True, name="cam-path-loader").start()


def _reload_cam_path_map() -> None:
    try:
        from back.app.services.db_pool import fetch_all
        rows = fetch_all(
            "SELECT c.name, c.unique_code, sp.path AS mediamtx_path "
            "FROM cameras c "
            "LEFT JOIN stream_paths sp ON sp.resource_id = c.id "
            "  AND sp.resource_type = 'camera' AND sp.active = true "
            "  AND upper(sp.path) NOT LIKE '%/INFERENCE' "
            "WHERE c.active = true AND c.deleted_at IS NULL",
        )
        mapping: dict[str, str] = {}
        for row in rows:
            name = row.get("name") or ""
            unique_code = row.get("unique_code") or ""
            mediamtx_path = row.get("mediamtx_path") or unique_code or name
            if name:
                mapping[name] = mediamtx_path
            if unique_code:
                mapping[unique_code] = mediamtx_path
        with _CAM_PATH_LOCK:
            _CAM_PATH_MAP.clear()
            _CAM_PATH_MAP.update(mapping)
    except Exception:
        pass


def _cam_path_map_refresh_loop() -> None:
    _reload_cam_path_map()
    while True:
        time.sleep(120)
        _reload_cam_path_map()


# ---------------------------------------------------------------------------
# Helpers de inferencia
# ---------------------------------------------------------------------------

def _strip_camera_inference_suffix(value: Any) -> str:
    base = re.sub(r"\s*-\s*INF\s*$", "", _text(value)).strip()
    return re.sub(r"/+INFERENCE(?:_VIEW)?\s*$", "", base, flags=re.IGNORECASE).strip()


def _camera_inference_stream_path(path: str) -> str:
    base = _strip_camera_inference_suffix(path).strip("/")
    return f"{base}{INFERENCE_SUFFIX}" if base else ""


def _camera_name_with_inference(value: Any, enabled: bool) -> str:
    base_name = _strip_camera_inference_suffix(value)
    if not base_name:
        return ""
    return f"{base_name} - INF" if enabled else base_name


def _camera_db_inference_type(value: Any, enabled: bool | None = None, fallback: Any = "inactiva") -> str:
    normalized = _text(value).strip().lower()
    if normalized in CAMERA_INFERENCE_TYPE_BY_UI:
        return CAMERA_INFERENCE_TYPE_BY_UI[normalized]
    if normalized in CAMERA_DB_INFERENCE_TYPES:
        return normalized
    if enabled is False:
        return "inactiva"
    fallback_value = _text(fallback).strip().lower()
    return fallback_value if fallback_value in CAMERA_DB_INFERENCE_TYPES else "inactiva"


def _camera_ui_inference_type(value: Any) -> str:
    normalized = _text(value).strip().lower()
    if normalized in CAMERA_INFERENCE_TYPE_BY_UI:
        return normalized
    return CAMERA_UI_INFERENCE_TYPE_BY_DB.get(normalized, "none")


def _ensure_inference_view_schema() -> None:
    global _INFERENCE_VIEW_SCHEMA_READY
    if _INFERENCE_VIEW_SCHEMA_READY:
        return
    with _INFERENCE_VIEW_SCHEMA_LOCK:
        if _INFERENCE_VIEW_SCHEMA_READY:
            return
        from back.app.services.db_pool import execute
        execute(
            """
            CREATE TABLE IF NOT EXISTS camera_inference_view_requests (
                camera_unique_code text PRIMARY KEY,
                inference_type text NOT NULL DEFAULT '',
                active boolean NOT NULL DEFAULT true,
                requested_until timestamptz NOT NULL,
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        _INFERENCE_VIEW_SCHEMA_READY = True


def _set_camera_inference_view_request(camera_key: Any, inference_type: Any = "", active: bool = True) -> None:
    camera_unique_code = _strip_camera_inference_suffix(_text(camera_key)).strip()
    if not camera_unique_code:
        return
    _ensure_inference_view_schema()
    from back.app.services.db_pool import execute
    if active:
        execute(
            """
            INSERT INTO camera_inference_view_requests
                (camera_unique_code, inference_type, active, requested_until, updated_at)
            VALUES (%s, %s, true, now() + (%s || ' seconds')::interval, now())
            ON CONFLICT (camera_unique_code) DO UPDATE SET
                inference_type = EXCLUDED.inference_type,
                active = true,
                requested_until = EXCLUDED.requested_until,
                updated_at = now()
            """,
            (camera_unique_code, _text(inference_type), str(_INFERENCE_VIEW_TTL_SECONDS)),
        )
    else:
        execute(
            """
            INSERT INTO camera_inference_view_requests
                (camera_unique_code, inference_type, active, requested_until, updated_at)
            VALUES (%s, %s, false, now(), now())
            ON CONFLICT (camera_unique_code) DO UPDATE SET
                active = false,
                requested_until = now(),
                updated_at = now()
            """,
            (camera_unique_code, _text(inference_type)),
        )


def _ensure_camera_notification_columns() -> None:
    global _CAMERA_NOTIF_SCHEMA_READY
    if _CAMERA_NOTIF_SCHEMA_READY:
        return
    with _CAMERA_NOTIF_SCHEMA_LOCK:
        if _CAMERA_NOTIF_SCHEMA_READY:
            return
        from back.app.services.db_pool import execute
        execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS notification_telegram boolean NOT NULL DEFAULT true")
        execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS notification_email boolean NOT NULL DEFAULT true")
        _CAMERA_NOTIF_SCHEMA_READY = True


def _update_camera_inference_by_name(camera_name: Any, inference_type: Any) -> tuple[dict[str, Any] | None, str]:
    normalized_name = _text(camera_name).strip()
    normalized_lookup = _strip_camera_inference_suffix(normalized_name).strip()
    normalized_inference_type = _camera_db_inference_type(inference_type)
    if not normalized_lookup:
        return None, "camera_not_found"
    try:
        from back.app.services.db_pool import execute_returning
        rows = execute_returning(
            """
            UPDATE cameras SET inference_type = %s
            WHERE lower(trim(name)) = lower(trim(%s)) OR lower(trim(unique_code)) = lower(trim(%s))
            RETURNING id, name, unique_code, inference_type
            """,
            (normalized_inference_type, normalized_lookup, normalized_lookup),
        )
    except Exception as exc:
        return None, f"camera_inference_update_failed: {_text(exc)}"
    if not rows:
        return None, "camera_not_found"
    row = dict(rows[0])
    return {
        "id": _text(row.get("id")),
        "source_id": _text(row.get("id")),
        "name": row.get("name"),
        "nombre": row.get("name"),
        "display_name": row.get("name"),
        "codigo_unico": row.get("unique_code"),
        "codigo": row.get("unique_code"),
        "path": row.get("unique_code"),
        "inference_type": row.get("inference_type"),
        "tipo_inferencia": row.get("inference_type"),
        "hacer_inferencia": _text(row.get("inference_type")) != "inactiva",
    }, ""


def _sync_camera_inference_runtime_request(camera: dict[str, Any] | None) -> None:
    if not camera:
        return
    key = _camera_control_key(camera)
    if not key:
        return
    inference_type = _camera_db_inference_type(camera.get("inference_type") or camera.get("tipo_inferencia"))
    try:
        _set_camera_inference_view_request(key, inference_type, active=inference_type != "inactiva")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers MediaMTX
# ---------------------------------------------------------------------------

def _mediamtx_api_base_url() -> str:
    base_url = _text(getattr(settings, "mediamtx_api_url", "")).strip()
    if base_url:
        return base_url.rstrip("/")
    port = int(getattr(settings, "mediamtx_api_port", 9997) or 9997)
    return f"http://127.0.0.1:{port}"


def _mediamtx_api_json(path: str, *, method: str = "GET", timeout: float = 2.0) -> dict[str, Any]:
    url = f"{_mediamtx_api_base_url()}/{path.lstrip('/')}"
    request = UrlRequest(url, method=method)
    if method.upper() in {"POST", "PUT", "PATCH"}:
        request.data = b""
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def _related_webrtc_paths(path: str) -> set[str]:
    normalized = _text(path).strip("/")
    if not normalized:
        return set()
    base = _strip_camera_inference_suffix(normalized).strip("/")
    paths = {normalized}
    if base:
        paths.add(base)
        paths.add(f"{base}{INFERENCE_SUFFIX}")
    return {item for item in paths if item}


def _kick_webrtc_readers_for_path(path: str) -> int:
    targets = _related_webrtc_paths(path)
    if not targets:
        return 0
    try:
        payload = _mediamtx_api_json("/v3/webrtcsessions/list")
    except Exception:
        return 0
    kicked = 0
    for session in payload.get("items") or []:
        session_path = _text(session.get("path")).strip("/")
        session_id = _text(session.get("id"))
        if not session_id or session_path not in targets:
            continue
        try:
            _mediamtx_api_json(f"/v3/webrtcsessions/kick/{quote(session_id, safe='')}", method="POST")
            kicked += 1
        except Exception:
            continue
    return kicked


def _mediamtx_path_has_source(path: str) -> bool:
    normalized = _text(path).strip("/")
    if not normalized:
        return False
    try:
        data = _mediamtx_api_json(f"/v3/paths/get/{quote(normalized, safe='')}")
        source = data.get("source") or {}
        return bool(source.get("type") or source.get("id"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lookup de cámara y helpers de viewer
# ---------------------------------------------------------------------------

def _camera_lookup(request: Request, *, camera: str = "", camera_id: int = 0, camera_name: str = "") -> dict[str, Any] | None:
    token = get_token(request)
    if not token:
        return None
    items = json.loads(build_context(request)["__CAMERA_ITEMS_JSON__"])
    camera_candidate = _text(camera).strip()
    camera_path_candidate = camera_candidate.strip("/")
    name_candidate = _text(camera_name).strip()
    for item in items:
        if camera_id and int(item.get("id") or 0) == int(camera_id):
            return item
    if camera_candidate:
        for item in items:
            path_names = {
                _text(item.get("path")).strip("/"),
                _text(item.get("mediamtx_path")).strip("/"),
                _text(item.get("codigo_unico")).strip("/"),
                _text(item.get("source_id")).strip(),
            }
            if camera_candidate in path_names or camera_path_candidate in path_names:
                return item
    candidates = [name_candidate, camera_candidate]
    for item in items:
        item_names = {
            _text(item.get("name")),
            _text(item.get("display_name")),
            _text(item.get("path")),
            _text(item.get("codigo_unico")),
        }
        if any(c and c in item_names for c in candidates):
            return item
    return None


def _camera_stream_path(item: dict[str, Any] | None, fallback: str = "") -> str:
    if not item:
        return _text(fallback).strip("/")
    return _text(
        item.get("path") or item.get("mediamtx_path") or item.get("codigo_unico") or item.get("name") or fallback
    ).strip("/")


def _camera_control_key(item: dict[str, Any] | None, fallback: Any = "") -> str:
    if item:
        value = (
            item.get("unique_code") or item.get("codigo_unico") or item.get("path")
            or item.get("mediamtx_path") or item.get("name")
        )
    else:
        value = fallback
    return _strip_camera_inference_suffix(_text(value)).strip("/")


def _camera_inference_db_row(*, camera: str = "", camera_name: str = "", item: dict[str, Any] | None = None) -> dict[str, Any] | None:
    candidates = {
        _strip_camera_inference_suffix(camera).strip("/"),
        _strip_camera_inference_suffix(camera_name).strip("/"),
    }
    if item:
        for key in ("name", "display_name", "unique_code", "codigo_unico", "path", "mediamtx_path"):
            value = _strip_camera_inference_suffix(item.get(key)).strip("/")
            if value:
                candidates.add(value)
    candidates = {v.strip().lower() for v in candidates if v}
    if not candidates:
        return None
    placeholders = ", ".join(["%s"] * len(candidates))
    params = list(candidates) + list(candidates)
    try:
        from back.app.services.db_pool import fetch_all
        rows = fetch_all(
            f"""
            SELECT id, name, unique_code, inference_type
            FROM cameras
            WHERE lower(trim(name)) IN ({placeholders})
               OR lower(trim(unique_code)) IN ({placeholders})
            ORDER BY created_at DESC NULLS LAST, name
            LIMIT 1
            """,
            params,
        )
    except Exception:
        return None
    return dict(rows[0]) if rows else None


def _camera_inference_state_payload(request: Request, *, camera: str = "", camera_id: int = 0, camera_name: str = "") -> dict[str, Any]:
    item = _camera_lookup(request, camera=camera, camera_id=camera_id, camera_name=camera_name)
    row = _camera_inference_db_row(camera=camera, camera_name=camera_name, item=item)
    control_key = _camera_control_key(row or item, camera or camera_name)
    db_inference_type = _camera_db_inference_type(
        (row or {}).get("inference_type") or (item or {}).get("inference_type")
        or (item or {}).get("tipo_inferencia") or "inactiva"
    )
    inference_path = _camera_inference_stream_path(control_key)
    online = _mediamtx_path_has_source(inference_path)
    active = db_inference_type != "inactiva"
    return {
        "ok": True,
        "camera": (row or {}).get("name") or (item or {}).get("name") or camera_name or camera,
        "camera_name": (row or {}).get("name") or (item or {}).get("name") or camera_name or camera,
        "camera_unique_code": (row or {}).get("unique_code") or control_key,
        "path": control_key,
        "inference_path": inference_path,
        "inference_type": db_inference_type,
        "tipo_inferencia": db_inference_type,
        "ui_inference_type": _camera_ui_inference_type(db_inference_type),
        "hacer_inferencia": active,
        "online": online,
    }


def _video_unavailable_payload(message: str = "El video actualmente no se encuentra disponible.") -> dict[str, Any]:
    return {"error": "video_unavailable", "online": False, "message": message, "viewer_url": "", "viewer_html": message}


def _authorized_camera_viewer(
    request: Request,
    *,
    camera: str = "",
    camera_id: int = 0,
    camera_name: str = "",
    inference: bool = False,
    inference_type: str = "",
    exclusive: bool = False,
) -> dict[str, Any]:
    token = get_token(request)
    if not token:
        return {"error": "authentication_required", "message": "Sesion expirada", "viewer_url": "", "viewer_html": "Sesion expirada"}
    item = _camera_lookup(request, camera=camera, camera_id=camera_id, camera_name=camera_name)
    path = _camera_stream_path(item, camera or camera_name)
    if inference and path:
        path = _camera_inference_stream_path(path)
    if not path:
        return _video_unavailable_payload()
    if path.upper().rstrip("/").endswith(INFERENCE_SUFFIX):
        try:
            mediamtx_data = _mediamtx_api_json(f"/v3/paths/get/{quote(path, safe='')}")
            source = mediamtx_data.get("source") or {}
            path_ready = bool(source.get("type") or source.get("id"))
        except Exception:
            path_ready = False
        if not path_ready:
            return _video_unavailable_payload()
        webrtc_base = _text(getattr(settings, "mediamtx_webrtc_base_url", "/mediamtx")).rstrip("/")
        viewer_url = f"{webrtc_base}/{quote(path, safe='/')}/"
        kicked_sessions = _kick_webrtc_readers_for_path(path) if exclusive else 0
        return {
            "online": True, "path": path, "inference_type": _text(inference_type),
            "exclusive": bool(exclusive), "kicked_sessions": kicked_sessions,
            "token": "", "expires_in": None, "viewer_url": viewer_url, "stream_url": viewer_url,
            "message": "Video disponible",
        }
    encoded_path = quote(path, safe="")
    try:
        status_payload = call_api(f"/streams/{encoded_path}/status", token=token) or {}
    except Exception:
        return _video_unavailable_payload()
    if status_payload.get("online") is not True:
        return _video_unavailable_payload()
    try:
        token_payload = call_api(f"/stream/token/{encoded_path}", method="POST", token=token) or {}
    except Exception:
        return _video_unavailable_payload("No se pudo generar el token de visualización para este video.")
    viewer_url = _text(token_payload.get("viewer_url"))
    if not viewer_url:
        return _video_unavailable_payload("No se pudo generar el enlace protegido para este video.")
    kicked_sessions = _kick_webrtc_readers_for_path(path) if exclusive else 0
    return {
        "online": True, "path": path, "inference_type": _text(inference_type),
        "exclusive": bool(exclusive), "kicked_sessions": kicked_sessions,
        "token": _text(token_payload.get("token")), "expires_in": token_payload.get("expires_in"),
        "viewer_url": viewer_url, "stream_url": viewer_url, "message": "Video disponible",
    }


def _mediamtx_page_url(viewer_url: str) -> str:
    return viewer_url.replace("/whep", "", 1) if "/whep" in viewer_url else viewer_url


def _camera_preview_document(payload: dict[str, Any]) -> str:
    from html import escape
    message = _text(payload.get("message")) or "El video actualmente no se encuentra disponible."
    if payload.get("online") is not True:
        return (
            "<!doctype html><html><head><meta charset='utf-8'><style>"
            "html,body{height:100%;margin:0;background:#050709;color:#d7dee8;font:700 12px system-ui;"
            "display:grid;place-items:center;text-align:center;padding:10px;box-sizing:border-box}"
            f"</style></head><body>{escape(message)}</body></html>"
        )
    viewer_url = _mediamtx_page_url(_text(payload.get("viewer_url")))
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "html,body,iframe{width:100%;height:100%;margin:0;border:0;background:#050709;overflow:hidden}"
        f"</style></head><body><iframe src='{escape(viewer_url)}' "
        "allow='autoplay; fullscreen; picture-in-picture'></iframe></body></html>"
    )


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _ffmpeg_jpeg(rtsp_url: str) -> bytes | None:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-fflags", "nobuffer", "-flags", "low_delay",
             "-analyzeduration", "500000", "-probesize", "500000",
             "-rtsp_transport", "tcp", "-i", rtsp_url,
             "-vframes", "1", "-vf", "scale=240:135", "-q:v", "9",
             "-update", "1", "-f", "image2", tmp],
            capture_output=True, timeout=5,
        )
        if os.path.exists(tmp) and os.path.getsize(tmp) > 100:
            with open(tmp, "rb") as fh:
                return fh.read()
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return None


def _refresh_snapshot(key: str, rtsp_url: str) -> None:
    try:
        jpeg = _ffmpeg_jpeg(rtsp_url)
        if jpeg:
            with _SNAPSHOT_LOCK:
                _SNAPSHOT_STORE[key] = (jpeg, time.monotonic())
    finally:
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_REFRESHING.discard(key)


# ---------------------------------------------------------------------------
# Helpers de formulario de cámara
# ---------------------------------------------------------------------------

def _camera_payload_from_form(p: dict[str, Any], token: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    companies = companies_for_options(token)
    vehicles = (call_api("/vehicles", token=token) or []) + (call_api("/drones", token=token) or [])
    rboxes = call_api("/rboxes", token=token) or []
    return camera_form_mapper.api_payload(
        p,
        companies=companies,
        vehicles=vehicles,
        rboxes=rboxes,
        default_company_id=ensure_company(token)["id"],
        existing=existing,
    )


# ---------------------------------------------------------------------------
# Rutas de cámaras
# ---------------------------------------------------------------------------

@router.get("/camera-form-options")
def camera_form_options(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies = companies_for_options(token)
        users = call_api("/users", token=token) or []
        vehicles = call_api("/vehicles", token=token) or []
        rboxes = call_api("/rboxes", token=token) or []
    except RuntimeError as exc:
        if auth_json_response() and False:
            pass
        from back.app.context import is_auth_error, auth_json_response
        if is_auth_error(exc):
            return auth_json_response()
        raise
    return {
        "owners": [{"id": _num_id(u.get("id")), "source_id": u.get("id"), "nombre_usuario": u.get("username"), "username": u.get("username")} for u in users],
        "organizations": [empresa_mapper.item(c) for c in companies],
        "camera_types": [
            {"id": 1, "codigo": "fixed", "nombre": "Cámara fija"},
            {"id": 2, "codigo": "ptz", "nombre": "Cámara PTZ"},
            {"id": 3, "codigo": "vehicle", "nombre": "Montada en vehículo"},
            {"id": 4, "codigo": "custom", "nombre": "Personalizada"},
        ],
        "protocols": [
            {"id": 1, "codigo": "rtsp", "nombre": "RTSP", "puerto_default": 554},
            {"id": 2, "codigo": "rtmp", "nombre": "RTMP", "puerto_default": settings.mediamtx_rtmp_port},
            {"id": 3, "codigo": "webrtc", "nombre": "WebRTC/WHEP", "puerto_default": urlparse(settings.mediamtx_webrtc_base_url).port or 8889},
        ],
        "vehicles": [normalize_vehicle_item(v) for v in vehicles] + [normalize_drone_item(d) for d in (call_api("/drones", token=token) or [])],
        "rboxes": [rbox_mapper.item(r) for r in rboxes],
        "brand_presets": [
            {"code": "hikvision", "label": "Hikvision", "default_port": 554, "supports_channel": True, "supports_substream": True},
            {"code": "dahua", "label": "Dahua", "default_port": 554, "supports_channel": True, "supports_substream": True},
            {"code": "custom_path", "label": "Personalizado", "default_port": 554, "supports_substream": True, "requires_custom_path": True},
        ],
        "stream_server": {"webrtc_base_url": settings.mediamtx_webrtc_base_url, "ip_publica": settings.public_host, "nombre": "MediaMTX"},
    }


@router.post("/camera-rtsp-preview")
async def camera_rtsp_preview(request: Request):
    return camera_form_mapper.rtsp_preview(await request.json())


@router.get("/cameras")
def cameras_registry(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        cams = call_api("/cameras", token=token) or []
        stream_configs = call_api("/stream-configs", token=token) or []
    except RuntimeError as exc:
        from back.app.context import is_auth_error, auth_json_response
        if is_auth_error(exc):
            return auth_json_response()
        raise
    db_items, error = db_camera_items()
    if db_items:
        return db_items
    if not cams and error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    stream_by_camera = {str(item.get("camera_id")): item for item in stream_configs if item.get("camera_id")}
    return [normalize_camera_item(cam, stream_by_camera.get(str(cam.get("id")))) for cam in cams]


@router.get("/camera-unique-codes")
def camera_unique_codes():
    codes, error = fetch_db_camera_unique_codes()
    if error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    return {"items": [{"value": code, "label": code} for code in codes], "total": len(codes)}


@router.get("/camera-names")
def camera_names():
    names, error = fetch_db_camera_names()
    if error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    return {"items": [{"value": name, "label": name} for name in names], "total": len(names)}


@router.post("/cameras")
async def camera_create(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    cameras = call_api("/cameras", token=token) or []
    explicit_camera_id = _text(p.get("camera_id") or p.get("source_id")).strip()
    if explicit_camera_id:
        source_id = resolve_source_id(cameras, explicit_camera_id)
        if not source_id:
            return JSONResponse({"error": "camera_not_found"}, status_code=404)
        existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None)
        if existing:
            p["codigo_unico"] = existing.get("unique_code") or p.get("codigo_unico")
        data = _camera_payload_from_form(p, token, existing)
        try:
            camera = call_api(f"/cameras/{source_id}", method="PUT", token=token, data=data)
        except RuntimeError as exc:
            return api_error_response(exc)
        return JSONResponse({"camera": normalize_camera_item(camera, {"path": camera.get("unique_code")})})
    data = _camera_payload_from_form(p, token)
    unique_code = _text(data.get("unique_code")).lower()
    if unique_code:
        duplicated = next((item for item in cameras if _text(item.get("unique_code")).lower() == unique_code), None)
        if duplicated:
            return JSONResponse({"error": "camera_unique_code_already_exists"}, status_code=409)
    try:
        camera = call_api("/cameras", method="POST", token=token, data=data)
    except RuntimeError as exc:
        return api_error_response(exc)
    return JSONResponse({"camera": normalize_camera_item(camera, {"path": camera.get("unique_code")})}, status_code=201)


@router.put("/cameras/{camera_id}")
async def camera_update(camera_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    cameras = call_api("/cameras", token=token) or []
    source_id = resolve_source_id(cameras, camera_id)
    if not source_id:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)
    existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None)
    p = await request.json()
    if existing:
        p["codigo_unico"] = existing.get("unique_code") or p.get("codigo_unico")
    data = _camera_payload_from_form(p, token, existing)
    try:
        camera = call_api(f"/cameras/{source_id}", method="PUT", token=token, data=data)
    except RuntimeError as exc:
        return api_error_response(exc)
    return JSONResponse({"camera": normalize_camera_item(camera, {"path": camera.get("unique_code")})})


@router.patch("/cameras/{camera_id}/inference")
async def camera_inference_update(camera_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    inference_enabled = bool(p.get("hacer_inferencia"))
    raw_inference_type = p.get("inference_type") or p.get("tipo_inferencia")
    if raw_inference_type is None:
        return JSONResponse({"error": "missing_inference_type"}, status_code=400)
    requested_inference_type = _camera_db_inference_type(raw_inference_type, inference_enabled)
    if requested_inference_type == "inactiva":
        inference_enabled = False
    camera_name = _text(p.get("camera_name") or p.get("name")).strip()
    if not camera_name:
        cameras = call_api("/cameras", token=token) or []
        source_id = resolve_source_id(cameras, camera_id)
        existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None) if source_id else None
        camera_name = _text((existing or {}).get("name")).strip()
    if not camera_name:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)
    item, error = _update_camera_inference_by_name(camera_name, requested_inference_type)
    if error:
        return JSONResponse({"error": error, "name": camera_name}, status_code=404 if error == "camera_not_found" else 500)
    clear_context_cache()
    _sync_camera_inference_runtime_request(item)
    return JSONResponse({"camera": item})


@router.patch("/cameras/{camera_id}/notifications")
async def camera_notifications_update(camera_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    notif_telegram = bool(p.get("notification_telegram", True))
    notif_email = bool(p.get("notification_email", True))
    camera_name = _text(p.get("camera_name") or p.get("name")).strip()
    if not camera_name:
        return JSONResponse({"error": "camera_name_required"}, status_code=400)
    try:
        _ensure_camera_notification_columns()
        from back.app.services.db_pool import execute
        execute(
            """
            UPDATE cameras
            SET notification_telegram = %s,
                notification_email = %s,
                updated_at = now()
            WHERE name = %s OR unique_code = %s
            """,
            (notif_telegram, notif_email, camera_name, camera_name),
        )
    except Exception as exc:
        return JSONResponse({"error": f"db_error: {_text(exc)}"}, status_code=500)
    clear_context_cache()
    return JSONResponse({"ok": True, "notification_telegram": notif_telegram, "notification_email": notif_email})


@router.post("/camera-inference-by-name")
async def camera_inference_update_by_name(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    raw_inference_type = p.get("inference_type") or p.get("tipo_inferencia")
    if raw_inference_type is None:
        return JSONResponse({"error": "missing_inference_type"}, status_code=400)
    item, error = _update_camera_inference_by_name(p.get("camera_name") or p.get("name"), raw_inference_type)
    if error:
        return JSONResponse({"error": error, "name": _text(p.get("camera_name") or p.get("name"))},
                            status_code=404 if error == "camera_not_found" else 500)
    clear_context_cache()
    _sync_camera_inference_runtime_request(item)
    return JSONResponse({"camera": item})


@router.delete("/cameras/{camera_id}")
def camera_delete(camera_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    cameras = call_api("/cameras", token=token) or []
    source_id = resolve_source_id(cameras, camera_id)
    if not source_id:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)
    call_api(f"/cameras/{source_id}", method="DELETE", token=token)
    return {"ok": True}


@router.get("/camera-viewer-url")
def camera_viewer_url(
    request: Request, camera: str = "", camera_id: int = 0, camera_name: str = "",
    inference: bool = False, inference_type: str = "", exclusive: bool = False,
):
    return _authorized_camera_viewer(request, camera=camera, camera_id=camera_id, camera_name=camera_name,
                                     inference=inference, inference_type=inference_type, exclusive=exclusive)


@router.get("/mediamtx/stream-status")
async def mediamtx_stream_status(request: Request):
    """Return which MediaMTX paths currently have an active publisher."""
    if not get_token(request):
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        data = _mediamtx_api_json("/v3/paths/list", timeout=3.0)
        items = data.get("items") or []
        paths: dict[str, bool] = {}
        for item in items:
            name = _text(item.get("name")).strip("/")
            if not name or "/INFERENCE" in name.upper():
                continue
            source = item.get("source") or {}
            has_source = bool(source.get("type") or source.get("id"))
            paths[name] = bool(item.get("ready")) and has_source
        return JSONResponse({"ok": True, "paths": paths})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc), "paths": {}})


@router.get("/camera-inference-state")
def camera_inference_state(request: Request, camera: str = "", camera_id: int = 0, camera_name: str = ""):
    if not get_token(request):
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    return JSONResponse(
        _camera_inference_state_payload(request, camera=camera, camera_id=camera_id, camera_name=camera_name),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.post("/camera-inference-view-state")
async def camera_inference_view_state(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = await request.json()
    camera_key = payload.get("camera") or payload.get("camera_name") or payload.get("path")
    active = bool(payload.get("active"))
    inference_type = payload.get("inference_type") or payload.get("tipo_inferencia") or ""
    try:
        _set_camera_inference_view_request(camera_key, inference_type, active=active)
    except Exception as exc:
        return JSONResponse({"error": f"inference_view_state_failed: {_text(exc)}"}, status_code=500)
    return JSONResponse({"ok": True, "active": active})


@router.get("/camera-snapshot")
def camera_snapshot(request: Request, camera_name: str = "") -> Response:
    if not get_token(request):
        return Response(status_code=401)
    key = camera_name.strip()
    now = time.monotonic()
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_STORE.get(key)
        needs_refresh = cached is None or (now - cached[1]) > _SNAPSHOT_TTL
        is_refreshing = key in _SNAPSHOT_REFRESHING
    if needs_refresh and not is_refreshing:
        with _CAM_PATH_LOCK:
            mediamtx_path = _CAM_PATH_MAP.get(key) or key
        rtsp_url = f"rtsp://127.0.0.1:8554/{mediamtx_path}" if mediamtx_path else None
        if rtsp_url and mediamtx_path:
            with _SNAPSHOT_LOCK:
                _SNAPSHOT_REFRESHING.add(key)
            _SNAPSHOT_POOL.submit(_refresh_snapshot, key, rtsp_url)
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_STORE.get(key)
    if cached:
        return Response(content=cached[0], media_type="image/jpeg", headers={"Cache-Control": "max-age=120"})
    return Response(content=_SNAPSHOT_PLACEHOLDER_SVG, media_type="image/svg+xml", headers={"Cache-Control": "max-age=5"})


@router.get("/camera-preview-frame", response_class=HTMLResponse)
def camera_preview_frame(
    request: Request, camera: str = "", camera_id: int = 0, camera_name: str = "",
    inference: bool = False, inference_type: str = "", exclusive: bool = False,
):
    payload = _authorized_camera_viewer(request, camera=camera, camera_id=camera_id, camera_name=camera_name,
                                        inference=inference, inference_type=inference_type, exclusive=exclusive)
    return HTMLResponse(_camera_preview_document(payload),
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


# ---------------------------------------------------------------------------
# RBox routes
# ---------------------------------------------------------------------------

@router.post("/rboxes")
async def rbox_create(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    companies = companies_for_options(token)
    company_id = resolve_source_id(companies, p.get("organizacion_id")) or ensure_company(token)["id"]
    rbox = call_api("/rboxes", method="POST", token=token, data=rbox_mapper.create_payload(p, company_id))
    return JSONResponse({"rbox": rbox_mapper.item(rbox)}, status_code=201)


@router.put("/rboxes/{rbox_id}")
async def rbox_update(rbox_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    rbox = call_api(f"/rboxes/{quote(rbox_id)}", method="PUT", token=token, data=rbox_mapper.update_payload(p))
    return JSONResponse({"rbox": rbox_mapper.item(rbox)})


@router.delete("/rboxes/{rbox_id}")
async def rbox_delete(rbox_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = call_api(f"/rboxes/{quote(rbox_id)}", method="DELETE", token=token)
    return JSONResponse(payload or {"message": "RBox eliminada"})
