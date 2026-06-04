from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from back.app.config import get_settings
from back.app.core.helpers import DashboardHelper
from back.app.domain.cameras import CameraFormMapper, CameraNormalizer
from back.app.domain.device_catalog import DeviceCatalogBuilder
from back.app.domain.drones.factory import DroneNormalizerFactory
from back.app.domain.empresa import EmpresaMapper, EmpresaService
from back.app.domain.rbox import RBoxMapper
from back.app.domain.streaming import StreamConfigMapper
from back.app.domain.vehicles import VehicleNormalizer
from back.app.domain.vehicles.telemetry import VehicleTelemetryMapper
from back.app.services.api_client import DashboardApiClient
from back.app.services.notification_settings import (
    add_email_recipient_to_db,
    add_telegram_chat_id_to_db,
    load_email_recipients_from_db,
    load_notification_settings,
    load_telegram_chat_ids_from_db,
    remove_email_recipient_from_db,
    remove_telegram_chat_id_from_db,
    save_notification_settings,
)
from back.app.services.remote_detection_feed import RemoteDetectionFeedService
from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
from back.app.services.rendering import DashboardTemplateRenderer
from back.app.services.send_mail import send_configured_email
from back.app.services.send_telegram import send_configured_telegram_alert

settings = get_settings()
SESSION_COOKIE = "robiotec_dashboard_token"
api_client = DashboardApiClient(settings)
remote_detection_feed = RemoteDetectionFeedService(settings)
remote_clip_telegram_notifier = RemoteClipTelegramNotifier(settings)
helper = DashboardHelper(SESSION_COOKIE)
camera_normalizer = CameraNormalizer()
vehicle_normalizer = VehicleNormalizer()
drone_normalizer = DroneNormalizerFactory(settings)
device_catalog = DeviceCatalogBuilder(settings)
camera_form_mapper = CameraFormMapper(helper, settings)
empresa_mapper = EmpresaMapper()
rbox_mapper = RBoxMapper()
stream_config_mapper = StreamConfigMapper()
vehicle_telemetry_mapper = VehicleTelemetryMapper()

CAMERA_INFERENCE_TYPE_BY_UI = {
    "none": "inactiva",
    "plates": "placa",
    "faces": "rostro",
    "access": "zona",
    "hands_helmet": "movimiento",
}
CAMERA_DB_INFERENCE_TYPES = set(CAMERA_INFERENCE_TYPE_BY_UI.values())

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "front"
TEMPLATES = FRONT / "templates"
STATIC = FRONT / "static"
template_renderer = DashboardTemplateRenderer(TEMPLATES)

app = FastAPI(title="Robiotec Dashboard", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
app.mount("/icons", StaticFiles(directory=STATIC / "icons"), name="icons")

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def invalidate_context_on_write(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        with _CONTEXT_LOCK:
            _CONTEXT_CACHE.clear()
        if "/cameras" in request.url.path or "/rboxes" in request.url.path:
            threading.Thread(target=_reload_cam_path_map, daemon=True).start()
    return response


@app.on_event("startup")
def start_remote_clip_telegram_notifier() -> None:
    remote_clip_telegram_notifier.start()
    threading.Thread(target=_cam_path_map_refresh_loop, daemon=True, name="cam-path-loader").start()


@app.on_event("shutdown")
def stop_remote_clip_telegram_notifier() -> None:
    remote_clip_telegram_notifier.stop()


def _json(value: Any) -> str:
    return helper.to_json(value)


def _notification_email_rows_html(recipients: list[str]) -> str:
    if not recipients:
        return '<tr><td class="notification-email-empty" colspan="3">No hay correos configurados.</td></tr>'
    rows = []
    for index, recipient in enumerate(recipients, start=1):
        safe_recipient = escape(_text(recipient))
        rows.append(
            '<tr>'
            f'<td class="notification-email-index">{index}</td>'
            f'<td class="notification-email-address">{safe_recipient}</td>'
            '<td class="notification-email-action">'
            '<form action="/api/notification-email-recipients/delete-form" class="notification-email-remove-form" method="post">'
            f'<input type="hidden" name="email" value="{safe_recipient}" />'
            f'<button class="notification-email-remove" type="submit" data-email="{safe_recipient}">Quitar</button>'
            '</form>'
            '</td>'
            '</tr>'
        )
    return "".join(rows)


def _notification_telegram_rows_html(chat_ids: list[str]) -> str:
    if not chat_ids:
        return '<tr><td class="notification-email-empty" colspan="3">No hay IDs configurados.</td></tr>'
    rows = []
    for index, chat_id in enumerate(chat_ids, start=1):
        safe_chat_id = escape(_text(chat_id))
        rows.append(
            '<tr>'
            f'<td class="notification-email-index">{index}</td>'
            f'<td class="notification-email-address">{safe_chat_id}</td>'
            '<td class="notification-email-action">'
            '<form action="/api/notification-telegram-chat-ids/delete-form" class="notification-telegram-remove-form" method="post">'
            f'<input type="hidden" name="chat_id" value="{safe_chat_id}" />'
            f'<button class="notification-email-remove" type="submit" data-chat-id="{safe_chat_id}">Quitar</button>'
            '</form>'
            '</td>'
            '</tr>'
        )
    return "".join(rows)


def _api(path: str, *, method: str = "GET", token: str | None = None, data: Any = None) -> Any:
    return api_client.request(path, method=method, token=token, data=data)


def _token(request: Request) -> str | None:
    return helper.token(request)


def _require_token(request: Request) -> str | None:
    return _token(request)


def _is_auth_error(error: Exception | str) -> bool:
    return helper.is_auth_error(error)


def _auth_json_response() -> JSONResponse:
    return helper.auth_json_response()


def _api_error_response(error: Exception | str) -> JSONResponse:
    if _is_auth_error(error):
        return _auth_json_response()
    message = _text(error, "No se pudo completar la operacion")
    status_code = 502 if "no disponible" in message.lower() else 400
    return JSONResponse({"error": message, "detail": message}, status_code=status_code)


def _num_id(value: Any) -> int:
    return helper.num_id(value)


def _text(value: Any, fallback: str = "") -> str:
    return helper.text(value, fallback)


def _fetch_db_camera_rows() -> tuple[list[dict[str, Any]], str]:
    try:
        from back.app.services.conection_sql_postgrest import fetch_all
    except Exception as exc:
        return [], f"No se pudo importar el conector PostgreSQL: {_text(exc)}"

    try:
        rows = fetch_all(
            """
            SELECT *
            FROM cameras
            ORDER BY created_at NULLS LAST, name
            """
        )
    except Exception as exc:
        return [], f"No se pudieron consultar las cámaras en PostgreSQL: {_text(exc)}"

    return [dict(row) for row in (rows or [])], ""


def _fetch_db_camera_unique_codes() -> tuple[list[str], str]:
    rows, error = _fetch_db_camera_rows()
    if error:
        return [], error

    codes: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        value = _text((row or {}).get("unique_code")).strip()
        if value and value not in seen:
            seen.add(value)
            codes.append(value)
    return codes, ""


def _fetch_db_camera_names() -> tuple[list[str], str]:
    rows, error = _fetch_db_camera_rows()
    if error:
        return [], error

    names: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        value = _text((row or {}).get("name")).strip()
        if value and value not in seen:
            seen.add(value)
            names.append(value)
    return names, ""


def _template_source(name: str, seen: set[Path] | None = None) -> str:
    return template_renderer.source(name, seen)


def _camera_unique_code_options_html(codes: list[str]) -> str:
    options: list[str] = ['<option value="" selected>Todas las cámaras</option>']
    if not codes:
        return "".join(options)
    for code in codes:
        safe_code = escape(code)
        options.append(f'<option value="{safe_code}">{safe_code}</option>')
    return "".join(options)


def _camera_item(camera: dict[str, Any], stream: dict[str, Any] | None = None) -> dict[str, Any]:
    item = camera_normalizer.item(camera, stream)
    path = _text(item.get("path") or item.get("codigo_unico"))
    if path:
        item["url"] = f"{settings.mediamtx_webrtc_base_url.rstrip('/')}/{quote(path)}"
    return item


def _db_camera_items() -> tuple[list[dict[str, Any]], str]:
    rows, error = _fetch_db_camera_rows()
    if error:
        return [], error
    return [_camera_item(row, {"path": row.get("unique_code")}) for row in rows], ""


def _display_maps(token: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    companies = {str(item.get("id")): item for item in (_companies_for_options(token) or [])}
    users = {str(item.get("id")): item for item in (_api("/users", token=token) or [])}
    return companies, users


empresa_service = EmpresaService(_api)


def _resolve_source_id(items: list[dict[str, Any]], raw_id: Any) -> str | None:
    return helper.resolve_source_id(items, raw_id)


def _vehicle_item(vehicle: dict[str, Any], companies: dict[str, dict[str, Any]] | None = None, users: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    return vehicle_normalizer.item(vehicle, companies, users)


def _drone_item(
    drone: dict[str, Any],
    stream_config: dict[str, Any] | None = None,
    companies: dict[str, dict[str, Any]] | None = None,
    users: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return drone_normalizer.item(drone, stream_config, companies, users)


def _drone_camera_item(drone_item: dict[str, Any]) -> dict[str, Any]:
    return device_catalog.drone_camera_item(drone_item)


def _device_from_camera(item: dict[str, Any]) -> dict[str, Any]:
    return device_catalog.device_from_camera(item)


def _device_from_vehicle_item(item: dict[str, Any], camera: dict[str, Any] | None = None) -> dict[str, Any]:
    return device_catalog.device_from_vehicle(item, camera)


def _camera_switcher_fallback(camera_items: list[dict[str, Any]]) -> str:
    return device_catalog.camera_switcher_fallback(camera_items)


def _telemetry_device_key(item: dict[str, Any]) -> str:
    return _text(item.get("device_id") or item.get("api_device_id") or item.get("camera_name"))


def _merge_live_telemetry(base_items: list[dict[str, Any]], live_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {_telemetry_device_key(item): dict(item) for item in base_items if _telemetry_device_key(item)}
    for live in live_items:
        key = _telemetry_device_key(live)
        if not key:
            continue
        current = merged.get(key, {})
        current_extra = current.get("extra") if isinstance(current.get("extra"), dict) else {}
        live_extra = live.get("extra") if isinstance(live.get("extra"), dict) else {}
        merged[key] = {
            **current,
            **live,
            "device_id": key,
            "camera_id": live.get("camera_id") or current.get("camera_id"),
            "camera_name": _text(live.get("camera_name") or current.get("camera_name")),
            "viewer_url": _text(live.get("viewer_url") or current.get("viewer_url")),
            "source": _text(live.get("source") or current.get("source")),
            "display_name": _text(live.get("display_name") or current.get("display_name") or key),
            "capabilities": current.get("capabilities") or live.get("capabilities") or {},
            "extra": {**current_extra, **live_extra},
        }
    return list(merged.values())


_CONTEXT_CACHE: dict[str, tuple[dict, float]] = {}
_CONTEXT_TTL = 30.0
_CONTEXT_LOCK = threading.Lock()


def _build_context(request: Request) -> dict[str, str]:
    token = _token(request)
    if token:
        now = time.monotonic()
        with _CONTEXT_LOCK:
            cached = _CONTEXT_CACHE.get(token)
            if cached and (now - cached[1]) < _CONTEXT_TTL:
                return cached[0]

    result = _build_context_uncached(request)

    if token:
        with _CONTEXT_LOCK:
            _CONTEXT_CACHE[token] = (result, time.monotonic())
            # Evict tokens older than 5 minutes to avoid memory growth
            cutoff = time.monotonic() - 300
            stale = [k for k, v in _CONTEXT_CACHE.items() if v[1] < cutoff]
            for k in stale:
                del _CONTEXT_CACHE[k]

    return result


def _build_context_uncached(request: Request) -> dict[str, str]:
    token = _token(request)
    me = {}
    companies: list[dict[str, Any]] = []
    cameras: list[dict[str, Any]] = []
    streams: list[dict[str, Any]] = []
    vehicles: list[dict[str, Any]] = []
    drones: list[dict[str, Any]] = []
    if token:
        try:
            me = _api("/auth/me", token=token) or {}
            companies = _api("/companies", token=token) or []
            cameras = _api("/cameras", token=token) or []
            streams = _api("/stream-paths", token=token) or []
            vehicles = _api("/vehicles", token=token) or []
            drones = _api("/drones", token=token) or []
        except RuntimeError:
            pass
    db_camera_items_error = ""
    db_cameras, db_camera_items_error = _fetch_db_camera_rows()
    if db_cameras:
        cameras = db_cameras
    stream_by_resource: dict[str, dict[str, Any]] = {}
    for item in streams:
        resource_id = str(item.get("resource_id") or "")
        if not resource_id:
            continue
        path = _text(item.get("path") or item.get("mediamtx_path"))
        is_inference_path = path.upper().rstrip("/").endswith("/INFERENCE")
        current = stream_by_resource.get(resource_id)
        current_path = _text((current or {}).get("path") or (current or {}).get("mediamtx_path"))
        current_is_inference_path = current_path.upper().rstrip("/").endswith("/INFERENCE")
        if current is None or (current_is_inference_path and not is_inference_path):
            stream_by_resource[resource_id] = item
    try:
        stream_configs = _api("/stream-configs", token=token) if token else []
    except RuntimeError:
        stream_configs = []
    stream_by_drone = {str(item.get("drone_id")): item for item in (stream_configs or []) if item.get("drone_id")}
    try:
        companies_map, users_map = _display_maps(token) if token else ({}, {})
    except RuntimeError:
        companies_map, users_map = {}, {}
    vehicle_items = [_vehicle_item(item, companies_map, users_map) for item in vehicles]
    drone_items = [_drone_item(item, stream_by_drone.get(str(item.get("id"))), companies_map, users_map) for item in drones]
    camera_items = [_camera_item(item, stream_by_resource.get(str(item.get("id")))) for item in cameras]
    camera_items.extend(_drone_camera_item(item) for item in drone_items)
    default_camera = camera_items[0] if camera_items else None
    devices = [_device_from_camera(item) for item in camera_items]
    camera_by_vehicle = {}
    for camera in camera_items:
        for key in (
            camera.get("vehiculo_source_id"),
            camera.get("vehiculo_id"),
            camera.get("drone_source_id"),
            camera.get("drone_id"),
        ):
            normalized_key = _text(key)
            if normalized_key:
                camera_by_vehicle[normalized_key] = camera
    devices.extend(
        _device_from_vehicle_item(
            item,
            camera_by_vehicle.get(_text(item.get("source_id") or item.get("registration_id"))),
        )
        for item in vehicle_items + drone_items
    )
    username = _text(me.get("username"), "robiotec")
    role = ", ".join(me.get("roles") or ["master"])
    db_camera_codes, db_camera_codes_error = _fetch_db_camera_unique_codes()
    db_camera_names, db_camera_names_error = _fetch_db_camera_names()
    notification_settings = load_notification_settings()
    notification_email_recipients = notification_settings.get("email", {}).get("recipients") or []
    notification_telegram_chat_ids = notification_settings.get("telegram", {}).get("chat_ids") or []
    public_notification_settings = json.loads(_json(notification_settings))
    if isinstance(public_notification_settings.get("telegram"), dict):
        public_notification_settings["telegram"]["bot_token"] = ""
    return {
        "__AUTH_USERNAME__": username,
        "__DEVELOPER_MENU_LINK__": '<a class="sidebar-link" href="/usuarios"><span class="sidebar-icon">◎</span><span class="sidebar-link-copy"><strong>Usuarios</strong><span>Roles y accesos</span></span><span class="sidebar-link-tooltip">Usuarios</span></a><a class="sidebar-link" href="/registros"><span class="sidebar-icon">▦</span><span class="sidebar-link-copy"><strong>Registros</strong><span>Empresas y permisos</span></span><span class="sidebar-link-tooltip">Registros</span></a>',
        "__STATIC_ASSET_VERSION__": str(int(time.time())),
        "__CAMERA_ITEMS_JSON__": _json(camera_items),
        "__DEVICE_CATALOG_JSON__": _json(devices),
        "__DEFAULT_CAMERA_JSON__": _json(default_camera),
        "__TELEMETRY_REFRESH_MS__": "1000",
        "__ERROR_BLOCK__": "",
        "__CAMERA_STREAMS__": "",
        "__CAMERA_SWITCHER_FALLBACK__": _camera_switcher_fallback(camera_items),
        "__CAMERA_PAGE_ACTION__": '<button class="camera-register-open" id="camera-register-open" type="button">Registrar cámara</button>',
        "__CAMERA_ADMIN_MODAL__": _template_source("partials/camera_admin_modal.html"),
        "__CAMERA_ADMIN_ACCESS_NOTE__": "",
        "__PLATE_PREVIEW_CHOICES__": "",
        "__PLATE_PREVIEW_SELECTED__": "",
        "__WEB_APP_CONFIG__": "{}",
        "__TELEMETRY_FOCUS_RAIL__": _template_source("partials/telemetry_focus_rail.html"),
        "__ARCOM_MIN_ZOOM__": "11",
        "__TELEMETRY_MAP_MIN_ZOOM__": "6",
        "__TELEMETRY_MAP_MAX_ZOOM__": "18",
        "__THUNDERFOREST_API_KEY_JSON__": "null",
        "__PROFILE_DISPLAY_NAME__": username,
        "__PROFILE_USERNAME__": username,
        "__PROFILE_INITIALS__": (username[:2] or "RB").upper(),
        "__PROFILE_ROLE_LABEL__": role,
        "__PROFILE_ROLE_NOTE__": "Sesión conectada a API Central",
        "__PROFILE_USER_ID__": _text(me.get("id"), "--"),
        "__PROFILE_SESSION_STATUS__": "Activa",
        "__PROFILE_SESSION_STARTED__": "Ahora",
        "__PROFILE_SESSION_EXPIRES__": "JWT API Central",
        "__PROFILE_DB_STATUS__": "Conectada",
        "__PROFILE_CAMERA_TOTAL__": str(len(cameras)),
        "__PROFILE_DEVICE_TOTAL__": str(len(vehicles) + len(drones)),
        "__PROFILE_VIEWER_TOTAL__": str(len(streams)),
        "__HOME_CAMERA_OPTION_ITEMS__": _camera_unique_code_options_html(db_camera_codes),
        "__HOME_CAMERA_CODES_JSON__": _json(db_camera_codes),
        "__HOME_CAMERA_NAME_OPTION_ITEMS__": _camera_unique_code_options_html(db_camera_names),
        "__HOME_CAMERA_NAMES_JSON__": _json(db_camera_names),
        "__HOME_CAMERA_STATUS__": (
            db_camera_codes_error
            or db_camera_items_error
            or f"{len(db_camera_codes)} IDs únicos cargados desde PostgreSQL"
        ),
        "__HOME_CAMERA_NAME_STATUS__": (
            db_camera_names_error
            or db_camera_items_error
            or f"{len(db_camera_names)} nombres cargados desde PostgreSQL"
        ),
        "__NOTIFICATION_SETTINGS_JSON__": _json(public_notification_settings),
        "__NOTIFICATION_EMAIL_COUNT__": str(len(notification_email_recipients)),
        "__NOTIFICATION_EMAIL_ROWS__": _notification_email_rows_html(notification_email_recipients),
        "__NOTIFICATION_TELEGRAM_CHAT_ID_COUNT__": str(len(notification_telegram_chat_ids)),
        "__NOTIFICATION_TELEGRAM_CHAT_ID_ROWS__": _notification_telegram_rows_html(notification_telegram_chat_ids),
        "__NOTIFICATION_TELEGRAM_TOKEN__": "",
        "__USER_ADMIN_ACCESS_NOTE__": "",
        "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "",
        "__USER_ADMIN_MODE_LABEL__": "Master",
        "__USER_ADMIN_SCOPE_LABEL__": "Global",
        "__USER_ADMIN_SCOPE_ROLE__": role,
        "__ROLE_ADMIN_HERO_CARD__": _template_source("partials/user_admin_role_hero_card.html"),
        "__ROLE_ADMIN_SECTION__": _template_source("partials/user_admin_role_section.html"),
    }


def _render(request: Request, template: str) -> HTMLResponse | RedirectResponse:
    token = _require_token(request)
    if template != "login.html":
        if not token:
            return RedirectResponse("/login")
        try:
            _api("/auth/me", token=token)
        except RuntimeError as exc:
            if _is_auth_error(exc):
                response = RedirectResponse("/login")
                response.delete_cookie(SESSION_COOKIE)
                return response
            raise
    context = _build_context(request)
    source = template_renderer.render_source(template, context)
    return HTMLResponse(source)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _render(request, "index.html")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _render(request, "login.html")


@app.get("/perfil", response_class=HTMLResponse)
def perfil(request: Request):
    return _render(request, "perfil.html")


@app.get("/camaras", response_class=HTMLResponse)
def camaras(request: Request):
    return _render(request, "camaras.html")


@app.get("/mapa", response_class=HTMLResponse)
def mapa(request: Request):
    return _render(request, "mapa.html")


@app.get("/eventos", response_class=HTMLResponse)
def eventos(request: Request):
    return _render(request, "eventos.html")


@app.get("/registro-vehiculos", response_class=HTMLResponse)
def registro_vehiculos(request: Request):
    return _render(request, "registro_vehiculos.html")


@app.get("/usuarios", response_class=HTMLResponse)
def usuarios(request: Request):
    return _render(request, "usuarios.html")


@app.get("/notificaciones", response_class=HTMLResponse)
def notificaciones(request: Request):
    return _render(request, "notificaciones.html")


@app.get("/registros", response_class=HTMLResponse)
def registros(request: Request):
    return _render(request, "registros.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
async def api_login(request: Request) -> JSONResponse:
    payload = await request.json()
    username = _text(payload.get("identity") or payload.get("username"))
    password = _text(payload.get("password"))
    try:
        result = _api("/auth/login", method="POST", data={"username": username, "password": password})
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=401)
    response = JSONResponse({"ok": True, "redirect": "/"})
    response.set_cookie(SESSION_COOKIE, result["access_token"], httponly=True, samesite="lax")
    return response


@app.post("/api/logout")
def api_logout() -> JSONResponse:
    response = JSONResponse({"ok": True, "redirect": "/login"})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/auth/session")
def auth_session(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"authenticated": False}, status_code=401)
    me = _api("/auth/me", token=token)
    return {"authenticated": True, "user": {"username": me.get("username"), "roles": me.get("roles", [])}}


def _ensure_company(token: str) -> dict[str, Any]:
    return empresa_service.ensure_default(token)


def _companies_for_options(token: str) -> list[dict[str, Any]]:
    return empresa_service.options(token)


def _generated_device_id(prefix: str) -> str:
    return helper.generated_device_id(prefix)


def _camera_payload_from_form(p: dict[str, Any], token: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    companies = _companies_for_options(token)
    vehicles = (_api("/vehicles", token=token) or []) + (_api("/drones", token=token) or [])
    rboxes = _api("/rboxes", token=token) or []
    return camera_form_mapper.api_payload(
        p,
        companies=companies,
        vehicles=vehicles,
        rboxes=rboxes,
        default_company_id=_ensure_company(token)["id"],
        existing=existing,
    )


def _strip_camera_inference_suffix(value: Any) -> str:
    return re.sub(r"\s*-\s*INF\s*$", "", _text(value)).strip()


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


def _update_camera_inference_by_name(camera_name: Any, inference_type: Any) -> tuple[dict[str, Any] | None, str]:
    normalized_name = _text(camera_name).strip()
    normalized_inference_type = _camera_db_inference_type(inference_type)
    if not normalized_name:
        return None, "camera_not_found"
    try:
        from back.app.services.conection_sql_postgrest import execute_returning

        rows = execute_returning(
            """
            UPDATE cameras
            SET inference_type = %s
            WHERE lower(trim(name)) = lower(trim(%s))
            RETURNING id, name, inference_type
            """,
            (normalized_inference_type, normalized_name),
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
        "inference_type": row.get("inference_type"),
        "tipo_inferencia": row.get("inference_type"),
        "hacer_inferencia": _text(row.get("inference_type")) != "inactiva",
    }, ""


@app.get("/api/camera-form-options")
def camera_form_options(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies = _companies_for_options(token)
        users = _api("/users", token=token) or []
        vehicles = _api("/vehicles", token=token) or []
        rboxes = _api("/rboxes", token=token) or []
    except RuntimeError as exc:
        if _is_auth_error(exc):
            return _auth_json_response()
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
        "vehicles": [_vehicle_item(v) for v in vehicles] + [_drone_item(d) for d in (_api("/drones", token=token) or [])],
        "rboxes": [rbox_mapper.item(r) for r in rboxes],
        "brand_presets": [
            {"code": "hikvision", "label": "Hikvision", "default_port": 554, "supports_channel": True, "supports_substream": True},
            {"code": "dahua", "label": "Dahua", "default_port": 554, "supports_channel": True, "supports_substream": True},
            {"code": "custom_path", "label": "Personalizado", "default_port": 554, "supports_substream": True, "requires_custom_path": True},
        ],
        "stream_server": {"webrtc_base_url": settings.mediamtx_webrtc_base_url, "ip_publica": settings.public_host, "nombre": "MediaMTX"},
    }


@app.post("/api/camera-rtsp-preview")
async def camera_rtsp_preview(request: Request):
    return camera_form_mapper.rtsp_preview(await request.json())


@app.get("/api/cameras")
def cameras_registry(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        cams = _api("/cameras", token=token) or []
        stream_configs = _api("/stream-configs", token=token) or []
    except RuntimeError as exc:
        if _is_auth_error(exc):
            return _auth_json_response()
        raise
    db_camera_items, error = _db_camera_items()
    if db_camera_items:
        return db_camera_items
    if not cams and error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    stream_by_camera = {str(item.get("camera_id")): item for item in stream_configs if item.get("camera_id")}
    return [_camera_item(cam, stream_by_camera.get(str(cam.get("id")))) for cam in cams]


@app.get("/api/camera-unique-codes")
def camera_unique_codes():
    codes, error = _fetch_db_camera_unique_codes()
    if error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    return {"items": [{"value": code, "label": code} for code in codes], "total": len(codes)}


@app.get("/api/camera-names")
def camera_names():
    names, error = _fetch_db_camera_names()
    if error:
        return JSONResponse({"error": error, "items": [], "total": 0}, status_code=502)
    return {"items": [{"value": name, "label": name} for name in names], "total": len(names)}


@app.get("/api/notification-settings")
def notification_settings(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    settings_payload = load_notification_settings()
    if isinstance(settings_payload.get("telegram"), dict):
        settings_payload["telegram"]["bot_token"] = ""
    return settings_payload


@app.put("/api/notification-settings")
async def notification_settings_update(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    saved = save_notification_settings(payload if isinstance(payload, dict) else {})
    if isinstance(saved.get("telegram"), dict):
        saved["telegram"]["bot_token"] = ""
    return {"ok": True, "settings": saved}


@app.get("/api/notification-email-recipients")
def notification_email_recipients(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    recipients = load_email_recipients_from_db()
    if recipients is None:
        return JSONResponse({"ok": False, "error": "No se pudieron leer los correos desde PostgreSQL."}, status_code=502)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@app.post("/api/notification-email-recipients")
async def notification_email_recipient_create(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = add_email_recipient_to_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo agregar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@app.post("/api/notification-email-recipients/form")
def notification_email_recipient_create_form(request: Request, email: str = Form("")):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        add_email_recipient_to_db(email)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.delete("/api/notification-email-recipients")
async def notification_email_recipient_delete(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = remove_email_recipient_from_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@app.post("/api/notification-email-recipients/delete")
async def notification_email_recipient_delete_post(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = remove_email_recipient_from_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@app.post("/api/notification-email-recipients/delete-form")
def notification_email_recipient_delete_form(request: Request, email: str = Form("")):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        remove_email_recipient_from_db(email)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.get("/api/notification-telegram-chat-ids")
def notification_telegram_chat_ids(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    chat_ids = load_telegram_chat_ids_from_db()
    if chat_ids is None:
        return JSONResponse({"ok": False, "error": "No se pudieron leer los IDs de Telegram desde PostgreSQL."}, status_code=502)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@app.post("/api/notification-telegram-chat-ids")
async def notification_telegram_chat_id_create(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = add_telegram_chat_id_to_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo agregar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@app.post("/api/notification-telegram-chat-ids/form")
def notification_telegram_chat_id_create_form(request: Request, chat_id: str = Form("")):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        add_telegram_chat_id_to_db(chat_id)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.delete("/api/notification-telegram-chat-ids")
async def notification_telegram_chat_id_delete(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = remove_telegram_chat_id_from_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@app.post("/api/notification-telegram-chat-ids/delete")
async def notification_telegram_chat_id_delete_post(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = remove_telegram_chat_id_from_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@app.post("/api/notification-telegram-chat-ids/delete-form")
def notification_telegram_chat_id_delete_form(request: Request, chat_id: str = Form("")):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        remove_telegram_chat_id_from_db(chat_id)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.post("/api/notification-settings/test-email")
def notification_settings_test_email(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    try:
        sent = send_configured_email()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, "sent": sent, "total": len(sent)}


@app.post("/api/notification-settings/test-email-form")
def notification_settings_test_email_form(request: Request):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        send_configured_email()
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.post("/api/notification-settings/test-telegram")
def notification_settings_test_telegram(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    try:
        delivery = send_configured_telegram_alert()
    except SystemExit as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, **delivery}


@app.post("/api/notification-settings/test-telegram-form")
def notification_settings_test_telegram_form(request: Request):
    token = _token(request)
    if not token:
        return RedirectResponse("/login", status_code=303)
    try:
        send_configured_telegram_alert()
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@app.get("/api/notification-settings/clip-notifier-status")
def notification_settings_clip_notifier_status(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    return {"ok": True, **remote_clip_telegram_notifier.status()}


@app.post("/api/notification-settings/clip-notifier-check")
def notification_settings_clip_notifier_check(request: Request):
    token = _token(request)
    if not token:
        return _auth_json_response()
    try:
        result = remote_clip_telegram_notifier.check_once()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, **result, "status": remote_clip_telegram_notifier.status()}


@app.post("/api/cameras")
async def camera_create(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    cameras = _api("/cameras", token=token) or []
    explicit_camera_id = _text(p.get("camera_id") or p.get("source_id")).strip()
    if explicit_camera_id:
        source_id = _resolve_source_id(cameras, explicit_camera_id)
        if not source_id:
            return JSONResponse({"error": "camera_not_found"}, status_code=404)
        existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None)
        if existing:
            # El id_unico/codigo_unico es el publish path de MediaMTX: no se cambia en edicion.
            p["codigo_unico"] = existing.get("unique_code") or p.get("codigo_unico")
        data = _camera_payload_from_form(p, token, existing)
        try:
            camera = _api(
                f"/cameras/{source_id}",
                method="PUT",
                token=token,
                data=data,
            )
        except RuntimeError as exc:
            return _api_error_response(exc)
        return JSONResponse({"camera": _camera_item(camera, {"path": camera.get("unique_code")})})
    data = _camera_payload_from_form(p, token)
    unique_code = _text(data.get("unique_code")).lower()
    if unique_code:
        duplicated = next(
            (
                item
                for item in cameras
                if _text(item.get("unique_code")).lower() == unique_code
            ),
            None,
        )
        if duplicated:
            return JSONResponse({"error": "camera_unique_code_already_exists"}, status_code=409)
    try:
        camera = _api(
            "/cameras",
            method="POST",
            token=token,
            data=data,
        )
    except RuntimeError as exc:
        return _api_error_response(exc)
    return JSONResponse({"camera": _camera_item(camera, {"path": camera.get("unique_code")})}, status_code=201)


@app.post("/api/rboxes")
async def rbox_create(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    companies = _companies_for_options(token)
    company_id = _resolve_source_id(companies, p.get("organizacion_id")) or _ensure_company(token)["id"]
    rbox = _api(
        "/rboxes",
        method="POST",
        token=token,
        data=rbox_mapper.create_payload(p, company_id),
    )
    return JSONResponse(
        {"rbox": rbox_mapper.item(rbox)},
        status_code=201,
    )


@app.put("/api/rboxes/{rbox_id}")
async def rbox_update(rbox_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    rbox = _api(
        f"/rboxes/{quote(rbox_id)}",
        method="PUT",
        token=token,
        data=rbox_mapper.update_payload(p),
    )
    return JSONResponse({"rbox": rbox_mapper.item(rbox)})


@app.delete("/api/rboxes/{rbox_id}")
async def rbox_delete(rbox_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = _api(
        f"/rboxes/{quote(rbox_id)}",
        method="DELETE",
        token=token,
    )
    return JSONResponse(payload or {"message": "RBox eliminada"})


@app.put("/api/cameras/{camera_id}")
async def camera_update(camera_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    cameras = _api("/cameras", token=token) or []
    source_id = _resolve_source_id(cameras, camera_id)
    if not source_id:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)
    existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None)
    p = await request.json()
    if existing:
        # El id_unico/codigo_unico queda congelado desde la creacion.
        p["codigo_unico"] = existing.get("unique_code") or p.get("codigo_unico")
    data = _camera_payload_from_form(p, token, existing)
    try:
        camera = _api(f"/cameras/{source_id}", method="PUT", token=token, data=data)
    except RuntimeError as exc:
        return _api_error_response(exc)
    return JSONResponse({"camera": _camera_item(camera, {"path": camera.get("unique_code")})})


@app.patch("/api/cameras/{camera_id}/inference")
async def camera_inference_update(camera_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    inference_enabled = bool(p.get("hacer_inferencia"))
    raw_inference_type = p.get("inference_type") or p.get("tipo_inferencia")
    if raw_inference_type is None:
        return JSONResponse({"error": "missing_inference_type"}, status_code=400)
    requested_inference_type = _camera_db_inference_type(
        raw_inference_type,
        inference_enabled,
    )
    if requested_inference_type == "inactiva":
        inference_enabled = False

    camera_name = _text(p.get("camera_name") or p.get("name")).strip()
    if not camera_name:
        cameras = _api("/cameras", token=token) or []
        source_id = _resolve_source_id(cameras, camera_id)
        existing = next((item for item in cameras if str(item.get("id")) == str(source_id)), None) if source_id else None
        camera_name = _text((existing or {}).get("name")).strip()
    if not camera_name:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)

    item, error = _update_camera_inference_by_name(camera_name, requested_inference_type)
    if error:
        status_code = 404 if error == "camera_not_found" else 500
        return JSONResponse({"error": error, "name": camera_name}, status_code=status_code)
    return JSONResponse({"camera": item})


@app.post("/api/camera-inference-by-name")
async def camera_inference_update_by_name(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    raw_inference_type = p.get("inference_type") or p.get("tipo_inferencia")
    if raw_inference_type is None:
        return JSONResponse({"error": "missing_inference_type"}, status_code=400)
    item, error = _update_camera_inference_by_name(p.get("camera_name") or p.get("name"), raw_inference_type)
    if error:
        status_code = 404 if error == "camera_not_found" else 500
        return JSONResponse({"error": error, "name": _text(p.get("camera_name") or p.get("name"))}, status_code=status_code)
    return JSONResponse({"camera": item})


@app.delete("/api/cameras/{camera_id}")
def camera_delete(camera_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    cameras = _api("/cameras", token=token) or []
    source_id = _resolve_source_id(cameras, camera_id)
    if not source_id:
        return JSONResponse({"error": "camera_not_found"}, status_code=404)
    _api(f"/cameras/{source_id}", method="DELETE", token=token)
    return {"ok": True}


@app.get("/api/vehicle-form-options")
def vehicle_form_options(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies = _companies_for_options(token)
        users = _api("/users", token=token) or []
        cameras = cameras_registry(request)
    except RuntimeError as exc:
        if _is_auth_error(exc):
            return _auth_json_response()
        raise
    if isinstance(cameras, JSONResponse):
        return cameras
    return {
        "organizations": [empresa_mapper.item(c) for c in companies],
        "owners": [{"id": _num_id(u.get("id")), "source_id": u.get("id"), "nombre_usuario": u.get("username"), "username": u.get("username")} for u in users],
        "vehicle_types": [
            {"id": 1, "codigo": "drone_robiotec", "nombre": "Dron Robiotec", "categoria": "dron"},
            {"id": 2, "codigo": "drone_dji", "nombre": "Dron DJI", "categoria": "dron"},
            {"id": 3, "codigo": "auto", "nombre": "Vehículo terrestre", "categoria": "vehiculo"},
        ],
        "cameras": cameras,
        "api_defaults": {"default_drone_device_id": "drone"},
    }


@app.get("/api/vehicle-registry")
def vehicle_registry(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies, users = _display_maps(token)
        vehicles = [_vehicle_item(v, companies, users) for v in (_api("/vehicles", token=token) or [])]
        stream_configs = _api("/stream-configs", token=token) or []
        stream_by_drone = stream_config_mapper.by_drone(stream_configs)
        drones = [_drone_item(d, stream_by_drone.get(str(d.get("id"))), companies, users) for d in (_api("/drones", token=token) or [])]
    except RuntimeError as exc:
        if _is_auth_error(exc):
            return _auth_json_response()
        raise
    return vehicles + drones


@app.post("/api/vehicle-registry")
async def vehicle_create(request: Request):
    token = _token(request)
    p = await request.json()
    companies = _companies_for_options(token)
    users = _api("/users", token=token) or []
    company_id = _resolve_source_id(companies, p.get("organizacion_id")) or _ensure_company(token)["id"]
    owner_user_id = _resolve_source_id(users, p.get("propietario_usuario_id"))
    company = {"id": company_id}
    vehicle_type = _text(p.get("vehicle_type") or p.get("vehicle_type_code"), "auto")
    is_drone = vehicle_type.startswith("drone")
    label = _text(p.get("label"), "Unidad")
    provided_identifier = _text(p.get("identifier"))
    if vehicle_type == "drone_dji":
        identifier = provided_identifier or _generated_device_id("DJI")
    elif vehicle_type == "drone_robiotec":
        identifier = provided_identifier or _generated_device_id("DRN")
    else:
        identifier = provided_identifier or _generated_device_id("CAR")
    if is_drone:
        drone = _api(
            "/drones",
            method="POST",
            token=token,
            data={
                "company_id": company["id"],
                "owner_user_id": owner_user_id,
                "name": label,
                "provider": "dji" if vehicle_type == "drone_dji" else "robiotec",
                "unique_code": identifier,
                "drone_type": "dji" if vehicle_type == "drone_dji" else "robiotec",
                "model": _text(p.get("model") or p.get("modelo")) or None,
                "manufacturer": "DJI" if vehicle_type == "drone_dji" else "Robiotec",
                "public_ip": _text(p.get("public_ip") or p.get("ip_publica") or settings.public_host),
                "rtmp_port": int(p.get("rtmp_port") or p.get("puerto_rtmp") or settings.mediamtx_rtmp_port),
                "rtmp_path": _text(p.get("rtmp_path") or identifier),
                "unique_ip": _text(p.get("unique_ip") or p.get("ip_unica")) or None,
                "active": True,
                "can_publish": True,
            },
        )
        path = identifier
        try:
            _api("/stream-paths", method="POST", token=token, data=stream_config_mapper.drone_stream_path_payload(company["id"], drone["id"], path))
        except RuntimeError:
            pass
        rtmp_url = f"rtmp://{settings.public_host}:{settings.mediamtx_rtmp_port}/{identifier}" if vehicle_type == "drone_dji" else ""
        companies_map, users_map = _display_maps(token)
        return JSONResponse({"vehicle": _drone_item(drone, {"origin_url": rtmp_url, "mediamtx_path": path}, companies_map, users_map)}, status_code=201)
    vehicle = _api(
        "/vehicles",
        method="POST",
        token=token,
        data={
            "company_id": company["id"],
            "owner_user_id": owner_user_id,
            "name": label,
            "vehicle_type": vehicle_type,
            "unique_code": identifier,
            "plate": identifier,
            "model": _text(p.get("model") or p.get("modelo")) or None,
            "active": True,
            "can_publish": True,
        },
    )
    companies_map, users_map = _display_maps(token)
    return JSONResponse({"vehicle": _vehicle_item(vehicle, companies_map, users_map)}, status_code=201)


@app.put("/api/vehicle-registry/{registration_id}")
async def vehicle_update(registration_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    companies = _companies_for_options(token)
    users = _api("/users", token=token) or []
    company_id = _resolve_source_id(companies, p.get("organizacion_id"))
    owner_user_id = _resolve_source_id(users, p.get("propietario_usuario_id"))
    label = _text(p.get("label"), "Unidad")
    vehicle_type = _text(p.get("vehicle_type") or p.get("vehicle_type_code"), "auto")
    is_drone = vehicle_type.startswith("drone")
    if is_drone:
        data = {
            "name": label,
            "provider": "dji" if vehicle_type == "drone_dji" else "robiotec",
            "drone_type": "dji" if vehicle_type == "drone_dji" else "robiotec",
            "manufacturer": "DJI" if vehicle_type == "drone_dji" else "Robiotec",
            "model": _text(p.get("model") or p.get("modelo")) or None,
            "active": True,
            "can_publish": True,
        }
        if company_id:
            data["company_id"] = company_id
        if owner_user_id:
            data["owner_user_id"] = owner_user_id
        if vehicle_type == "drone_dji":
            data["public_ip"] = settings.public_host
            data["rtmp_port"] = settings.mediamtx_rtmp_port
        drone = _api(f"/drones/{registration_id}", method="PUT", token=token, data=data)
        stream_configs = _api("/stream-configs", token=token) or []
        stream_by_drone = stream_config_mapper.by_drone(stream_configs)
        companies_map, users_map = _display_maps(token)
        return JSONResponse({"vehicle": _drone_item(drone, stream_by_drone.get(str(drone.get("id"))), companies_map, users_map)})
    data = {"name": label, "vehicle_type": "auto", "model": _text(p.get("model") or p.get("modelo")) or None, "active": True, "can_publish": True}
    if company_id:
        data["company_id"] = company_id
    if owner_user_id:
        data["owner_user_id"] = owner_user_id
    vehicle = _api(f"/vehicles/{registration_id}", method="PUT", token=token, data=data)
    companies_map, users_map = _display_maps(token)
    return JSONResponse({"vehicle": _vehicle_item(vehicle, companies_map, users_map)})


@app.delete("/api/vehicle-registry/{registration_id}")
def vehicle_delete(registration_id: str, request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        _api(f"/vehicles/{registration_id}", method="DELETE", token=token)
    except RuntimeError as vehicle_error:
        if "no encontrado" not in str(vehicle_error).lower() and "not found" not in str(vehicle_error).lower():
            raise
        _api(f"/drones/{registration_id}", method="DELETE", token=token)
    return {"ok": True}


@app.get("/api/organizations")
def organizations(request: Request):
    token = _token(request)
    return [empresa_mapper.item(c) for c in _companies_for_options(token)]


@app.get("/api/users")
def users(request: Request):
    token = _token(request)
    return [{"id": _num_id(u.get("id")), "source_id": u.get("id"), "nombre_usuario": u.get("username"), "email": u.get("email"), "activo": u.get("active")} for u in (_api("/users", token=token) or [])]


@app.get("/api/user-role-options")
def user_role_options(request: Request):
    return {"roles": [{"id": i + 1, "codigo": role, "nombre": role} for i, role in enumerate(["master", "company_admin", "area_admin", "operator", "viewer"])]}


@app.get("/api/user-roles")
def user_roles(request: Request):
    return user_role_options(request)["roles"]


@app.get("/api/devices")
def devices(request: Request):
    return JSONResponse(json.loads(_build_context(request)["__DEVICE_CATALOG_JSON__"]))


@app.get("/api/events")
def events():
    return []


@app.get("/api/evidence")
def evidence():
    return []


@app.get("/api/camera-events")
def camera_events(request: Request, camera: str = "", camera_name: str = "", limit: int = 8):
    item = _camera_lookup(request, camera=camera, camera_name=camera_name)
    cam_id = _text(item.get("codigo_unico") or item.get("path") or item.get("name")) if item else _text(camera_name or camera)
    if not cam_id:
        return JSONResponse([], status_code=200)
    try:
        return JSONResponse(remote_detection_feed.fetch_camera_events(cam_id, limit=limit))
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": []}, status_code=503)


@app.get("/api/event-history")
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


@app.get("/api/event-history-filter-options")
def event_history_filter_options(field: str = ""):
    try:
        return JSONResponse(remote_detection_feed.fetch_event_history_filter_options(field))
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": [], "total": 0}, status_code=400)


@app.patch("/api/event-history/{event_id}/status")
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


@app.get("/api/camera-event-crop")
def camera_event_crop(path: str):
    try:
        content, media_type = remote_detection_feed.read_remote_file(path)
    except FileNotFoundError:
        return Response(status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/api/camera-event-video")
def camera_event_video(path: str):
    try:
        local_path, media_type = remote_detection_feed.cache_remote_video(path)
    except FileNotFoundError:
        return Response(status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return FileResponse(local_path, media_type=media_type)


@app.get("/api/telemetry")
def telemetry(request: Request):
    token = _token(request)
    devices = json.loads(_build_context(request)["__DEVICE_CATALOG_JSON__"])
    base_items = [item for item in (vehicle_telemetry_mapper.inventory_item(device) for device in devices) if item]
    try:
        live_items = _api("/telemetry/latest", token=token) or []
    except RuntimeError:
        live_items = []
    return _merge_live_telemetry(base_items, live_items if isinstance(live_items, list) else [])


@app.get("/api/arcom/concessions")
def arcom_concessions(bbox: str = "", limit: int = 120):
    try:
        return _api(f"/arcom/concessions?bbox={quote(bbox)}&limit={int(limit or 120)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@app.get("/api/arcom/concession-lookup")
def arcom_concession_lookup(lat: float, lon: float):
    try:
        return _api(f"/arcom/concession-lookup?lat={lat}&lon={lon}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "found": False, "concession": None}, status_code=503)


@app.get("/api/osint/layers")
def osint_layers(bbox: str = "", limit: int = 2000, layer: str = ""):
    try:
        return _api(f"/osint/layers?bbox={quote(bbox)}&limit={int(limit or 2000)}&layer={quote(layer)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@app.get("/api/osint/report")
def osint_report():
    try:
        return _api("/osint/report")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "available": False}, status_code=503)


@app.get("/api/tracks/drone")
def drone_tracks():
    return {}


@app.post("/api/tracks/drone/clear")
def drone_tracks_clear():
    return {"ok": True}


@app.get("/api/objetivos/{objective_id}")
def high_value_objective(objective_id: str):
    return {"id": _text(objective_id), "found": False, "points": []}


@app.post("/api/objetivos/{objective_id}/clear")
def high_value_objective_clear(objective_id: str):
    return {"id": _text(objective_id), "ok": True}


def _camera_lookup(request: Request, *, camera: str = "", camera_id: int = 0, camera_name: str = "") -> dict[str, Any] | None:
    token = _token(request)
    if not token:
        return None
    items = json.loads(_build_context(request)["__CAMERA_ITEMS_JSON__"])
    candidates = [_text(camera_name), _text(camera)]
    for item in items:
        if camera_id and int(item.get("id") or 0) == int(camera_id):
            return item
        item_names = {
            _text(item.get("name")),
            _text(item.get("display_name")),
            _text(item.get("path")),
            _text(item.get("codigo_unico")),
        }
        if any(candidate and candidate in item_names for candidate in candidates):
            return item
    return None


def _camera_stream_path(item: dict[str, Any] | None, fallback: str = "") -> str:
    if not item:
        return _text(fallback).strip("/")
    return _text(
        item.get("path")
        or item.get("mediamtx_path")
        or item.get("codigo_unico")
        or item.get("name")
        or fallback
    ).strip("/")


def _video_unavailable_payload(message: str = "El video actualmente no se encuentra disponible.") -> dict[str, Any]:
    return {
        "error": "video_unavailable",
        "online": False,
        "message": message,
        "viewer_url": "",
        "viewer_html": message,
    }


def _authorized_camera_viewer(
    request: Request,
    *,
    camera: str = "",
    camera_id: int = 0,
    camera_name: str = "",
    inference: bool = False,
    inference_type: str = "",
) -> dict[str, Any]:
    token = _token(request)
    if not token:
        return {"error": "authentication_required", "message": "Sesion expirada", "viewer_url": "", "viewer_html": "Sesion expirada"}
    item = _camera_lookup(request, camera=camera, camera_id=camera_id, camera_name=camera_name)
    path = _camera_stream_path(item, camera or camera_name)
    if inference and path and not path.upper().rstrip("/").endswith("/INFERENCE"):
        path = f"{path.rstrip('/')}/INFERENCE"
    if not path:
        return _video_unavailable_payload()
    encoded_path = quote(path, safe="")
    try:
        status_payload = _api(f"/streams/{encoded_path}/status", token=token) or {}
    except Exception:
        return _video_unavailable_payload()
    if status_payload.get("online") is not True:
        return _video_unavailable_payload()
    try:
        token_payload = _api(f"/stream/token/{encoded_path}", method="POST", token=token) or {}
    except Exception:
        return _video_unavailable_payload("No se pudo generar el token de visualización para este video.")
    viewer_url = _text(token_payload.get("viewer_url"))
    if not viewer_url:
        return _video_unavailable_payload("No se pudo generar el enlace protegido para este video.")
    return {
        "online": True,
        "path": path,
        "inference_type": _text(inference_type),
        "token": _text(token_payload.get("token")),
        "expires_in": token_payload.get("expires_in"),
        "viewer_url": viewer_url,
        "stream_url": viewer_url,
        "message": "Video disponible",
    }


def _mediamtx_page_url(viewer_url: str) -> str:
    if "/whep" in viewer_url:
        return viewer_url.replace("/whep", "", 1)
    return viewer_url


def _camera_preview_document(payload: dict[str, Any]) -> str:
    message = _text(payload.get("message")) or "El video actualmente no se encuentra disponible."
    if payload.get("online") is not True:
        return (
            "<!doctype html><html><head><meta charset='utf-8'><style>"
            "html,body{height:100%;margin:0;background:#050709;color:#d7dee8;font:700 12px system-ui;display:grid;place-items:center;text-align:center;padding:10px;box-sizing:border-box}"
            "</style></head><body>"
            f"{escape(message)}"
            "</body></html>"
        )
    viewer_url = _mediamtx_page_url(_text(payload.get("viewer_url")))
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "html,body,iframe{width:100%;height:100%;margin:0;border:0;background:#050709;overflow:hidden}"
        "</style></head><body>"
        f"<iframe src='{escape(viewer_url)}' allow='autoplay; fullscreen; picture-in-picture'></iframe>"
        "</body></html>"
    )


@app.get("/api/camera-viewer-url")
def camera_viewer_url(
    request: Request,
    camera: str = "",
    camera_id: int = 0,
    camera_name: str = "",
    inference: bool = False,
    inference_type: str = "",
):
    return _authorized_camera_viewer(
        request,
        camera=camera,
        camera_id=camera_id,
        camera_name=camera_name,
        inference=inference,
        inference_type=inference_type,
    )


_SNAPSHOT_STORE: dict[str, tuple[bytes, float]] = {}
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_REFRESHING: set[str] = set()
_SNAPSHOT_TTL = 180.0
_SNAPSHOT_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cam-snap")

# {camera_name: mediamtx_path}  — populated at startup, refreshed periodically
_CAM_PATH_MAP: dict[str, str] = {}
_CAM_PATH_LOCK = threading.Lock()


def _reload_cam_path_map() -> None:
    try:
        from back.app.services.conection_sql_postgrest import fetch_all as _db
        rows = _db(
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


def _ffmpeg_jpeg(rtsp_url: str) -> bytes | None:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-analyzeduration", "500000",
                "-probesize", "500000",
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                "-vframes", "1",
                "-vf", "scale=240:135",
                "-q:v", "9",
                "-update", "1",
                "-f", "image2",
                tmp,
            ],
            capture_output=True,
            timeout=5,
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


@app.get("/api/camera-snapshot")
def camera_snapshot(request: Request, camera_name: str = "") -> Response:
    if not _token(request):
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
        return Response(
            content=cached[0],
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=120"},
        )

    return Response(
        content=_SNAPSHOT_PLACEHOLDER_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "max-age=5"},
    )


@app.get("/api/camera-preview-frame", response_class=HTMLResponse)
def camera_preview_frame(
    request: Request,
    camera: str = "",
    camera_id: int = 0,
    camera_name: str = "",
    inference: bool = False,
    inference_type: str = "",
):
    payload = _authorized_camera_viewer(
        request,
        camera=camera,
        camera_id=camera_id,
        camera_name=camera_name,
        inference=inference,
        inference_type=inference_type,
    )
    return HTMLResponse(
        _camera_preview_document(payload),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def api_proxy(path: str, request: Request) -> Response:
    upstream_url = urljoin(f"{settings.api_base_url.rstrip('/')}/", path)
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"
    body = await request.body()
    headers = {key: value for key, value in request.headers.items() if key.lower() not in {"host", "content-length", "connection", "accept-encoding", "cookie"}}
    token = _token(request)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    upstream_request = UrlRequest(upstream_url, data=body if body else None, headers=headers, method=request.method)
    try:
        with urlopen(upstream_request, timeout=20) as upstream_response:
            return Response(content=upstream_response.read(), status_code=upstream_response.status, media_type=upstream_response.headers.get_content_type())
    except HTTPError as exc:
        return Response(content=exc.read(), status_code=exc.code, media_type=exc.headers.get_content_type() if exc.headers else "application/json")
    except URLError:
        return Response(content=b'{"detail":"API central no disponible"}', status_code=502, media_type="application/json")
