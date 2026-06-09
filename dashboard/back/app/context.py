"""
Helpers compartidos y construcción del contexto de página.

Contiene las funciones auxiliares que usan múltiples routers:
auth, normalización, llamadas API, caché de contexto y renderizado.
"""
from __future__ import annotations

import base64
import json
import threading
import time
from html import escape
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from back.app.state import (
    SESSION_COOKIE,
    api_client,
    camera_normalizer,
    device_catalog,
    drone_normalizer,
    empresa_mapper,
    empresa_service,
    helper,
    settings,
    stream_config_mapper,
    template_renderer,
    vehicle_normalizer,
    vehicle_telemetry_mapper,
)
from back.app.services.notification_settings import load_notification_settings

# ---------------------------------------------------------------------------
# Caché de contexto de página
# ---------------------------------------------------------------------------

_CONTEXT_CACHE: dict[str, tuple[dict, float]] = {}
_CONTEXT_TTL = 30.0
_CONTEXT_LOCK = threading.Lock()


def clear_context_cache() -> None:
    with _CONTEXT_LOCK:
        _CONTEXT_CACHE.clear()


# ---------------------------------------------------------------------------
# Helpers primitivos
# ---------------------------------------------------------------------------

def _json(value: Any) -> str:
    return helper.to_json(value)


def _text(value: Any, fallback: str = "") -> str:
    return helper.text(value, fallback)


def _num_id(value: Any) -> int:
    return helper.num_id(value)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_token(request: Request) -> str | None:
    return helper.token(request)


def get_token_roles(token: str) -> list[str]:
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))
        return payload.get("roles") or []
    except Exception:
        return []


def require_admin_role(token: str | None) -> bool:
    if not token:
        return False
    return bool({"master", "admin"}.intersection(get_token_roles(token)))


def is_auth_error(error: Exception | str) -> bool:
    return helper.is_auth_error(error)


def auth_json_response() -> JSONResponse:
    return helper.auth_json_response()


def api_error_response(error: Exception | str) -> JSONResponse:
    if is_auth_error(error):
        return auth_json_response()
    message = _text(error, "No se pudo completar la operacion")
    status_code = 502 if "no disponible" in message.lower() else 400
    return JSONResponse({"error": message, "detail": message}, status_code=status_code)


# ---------------------------------------------------------------------------
# API central
# ---------------------------------------------------------------------------

def call_api(path: str, *, method: str = "GET", token: str | None = None, data: Any = None) -> Any:
    return api_client.request(path, method=method, token=token, data=data)


# ---------------------------------------------------------------------------
# Normalización de entidades de dominio
# ---------------------------------------------------------------------------

def normalize_camera_item(camera: dict[str, Any], stream: dict[str, Any] | None = None) -> dict[str, Any]:
    from urllib.parse import quote
    item = camera_normalizer.item(camera, stream)
    path = _text(item.get("path") or item.get("codigo_unico"))
    if path:
        item["url"] = f"{settings.mediamtx_webrtc_base_url.rstrip('/')}/{quote(path)}"
    return item


def normalize_vehicle_item(
    vehicle: dict[str, Any],
    companies: dict[str, dict[str, Any]] | None = None,
    users: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return vehicle_normalizer.item(vehicle, companies, users)


def normalize_drone_item(
    drone: dict[str, Any],
    stream_config: dict[str, Any] | None = None,
    companies: dict[str, dict[str, Any]] | None = None,
    users: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return drone_normalizer.item(drone, stream_config, companies, users)


def drone_camera_item(drone_item: dict[str, Any]) -> dict[str, Any]:
    return device_catalog.drone_camera_item(drone_item)


def device_from_camera(item: dict[str, Any]) -> dict[str, Any]:
    return device_catalog.device_from_camera(item)


def device_from_vehicle(item: dict[str, Any], camera: dict[str, Any] | None = None) -> dict[str, Any]:
    return device_catalog.device_from_vehicle(item, camera)


def camera_switcher_fallback(camera_items: list[dict[str, Any]]) -> str:
    return device_catalog.camera_switcher_fallback(camera_items)


# ---------------------------------------------------------------------------
# DB helpers para cámaras
# ---------------------------------------------------------------------------

def fetch_db_camera_rows() -> tuple[list[dict[str, Any]], str]:
    try:
        from back.app.services.db_pool import fetch_all
    except Exception as exc:
        return [], f"No se pudo importar el conector PostgreSQL: {_text(exc)}"
    try:
        rows = fetch_all(
            "SELECT * FROM cameras ORDER BY created_at NULLS LAST, name"
        )
    except Exception as exc:
        return [], f"No se pudieron consultar las cámaras en PostgreSQL: {_text(exc)}"
    return [dict(row) for row in (rows or [])], ""


def fetch_db_camera_unique_codes() -> tuple[list[str], str]:
    rows, error = fetch_db_camera_rows()
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


def fetch_db_camera_names() -> tuple[list[str], str]:
    rows, error = fetch_db_camera_rows()
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


def db_camera_items() -> tuple[list[dict[str, Any]], str]:
    rows, error = fetch_db_camera_rows()
    if error:
        return [], error
    return [normalize_camera_item(row, {"path": row.get("unique_code")}) for row in rows], ""


# ---------------------------------------------------------------------------
# Empresa / compañías
# ---------------------------------------------------------------------------

def companies_for_options(token: str) -> list[dict[str, Any]]:
    return empresa_service.options(token)


def ensure_company(token: str) -> dict[str, Any]:
    return empresa_service.ensure_default(token)


def display_maps(token: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    companies = {str(item.get("id")): item for item in (companies_for_options(token) or [])}
    users = {str(item.get("id")): item for item in (call_api("/users", token=token) or [])}
    return companies, users


def resolve_source_id(items: list[dict[str, Any]], raw_id: Any) -> str | None:
    return helper.resolve_source_id(items, raw_id)


def generated_device_id(prefix: str) -> str:
    return helper.generated_device_id(prefix)


# ---------------------------------------------------------------------------
# HTML helpers para notificaciones
# ---------------------------------------------------------------------------

def notification_email_rows_html(recipients: list[str]) -> str:
    if not recipients:
        return '<tr><td class="notification-email-empty" colspan="3">No hay correos configurados.</td></tr>'
    rows = []
    for index, recipient in enumerate(recipients, start=1):
        safe = escape(_text(recipient))
        rows.append(
            f'<tr><td class="notification-email-index">{index}</td>'
            f'<td class="notification-email-address">{safe}</td>'
            '<td class="notification-email-action">'
            '<form action="/api/notification-email-recipients/delete-form" '
            'class="notification-email-remove-form" method="post">'
            f'<input type="hidden" name="email" value="{safe}" />'
            f'<button class="notification-email-remove" type="submit" data-email="{safe}">Quitar</button>'
            '</form></td></tr>'
        )
    return "".join(rows)


def notification_telegram_rows_html(chat_ids: list[str]) -> str:
    if not chat_ids:
        return '<tr><td class="notification-email-empty" colspan="3">No hay IDs configurados.</td></tr>'
    rows = []
    for index, chat_id in enumerate(chat_ids, start=1):
        safe = escape(_text(chat_id))
        rows.append(
            f'<tr><td class="notification-email-index">{index}</td>'
            f'<td class="notification-email-address">{safe}</td>'
            '<td class="notification-email-action">'
            '<form action="/api/notification-telegram-chat-ids/delete-form" '
            'class="notification-telegram-remove-form" method="post">'
            f'<input type="hidden" name="chat_id" value="{safe}" />'
            f'<button class="notification-email-remove" type="submit" data-chat-id="{safe}">Quitar</button>'
            '</form></td></tr>'
        )
    return "".join(rows)


def camera_unique_code_options_html(codes: list[str]) -> str:
    options = ['<option value="" selected>Todas las cámaras</option>']
    for code in codes:
        safe = escape(code)
        options.append(f'<option value="{safe}">{safe}</option>')
    return "".join(options)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def template_source(name: str, seen: set[Path] | None = None) -> str:
    return template_renderer.source(name, seen)


# ---------------------------------------------------------------------------
# Telemetría
# ---------------------------------------------------------------------------

def _telemetry_device_key(item: dict[str, Any]) -> str:
    return _text(item.get("device_id") or item.get("api_device_id") or item.get("camera_name"))


def merge_live_telemetry(
    base_items: list[dict[str, Any]], live_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
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


# ---------------------------------------------------------------------------
# Construcción del contexto de página
# ---------------------------------------------------------------------------

def build_context(request: Request) -> dict[str, str]:
    token = get_token(request)
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
            cutoff = time.monotonic() - 300
            stale = [k for k, v in _CONTEXT_CACHE.items() if v[1] < cutoff]
            for k in stale:
                del _CONTEXT_CACHE[k]

    return result


def _build_context_uncached(request: Request) -> dict[str, str]:
    token = get_token(request)
    me: dict[str, Any] = {}
    companies: list[dict[str, Any]] = []
    cameras: list[dict[str, Any]] = []
    streams: list[dict[str, Any]] = []
    vehicles: list[dict[str, Any]] = []
    drones: list[dict[str, Any]] = []

    if token:
        def _try_api(path: str) -> Any:
            try:
                return call_api(path, token=token) or []
            except RuntimeError:
                return []

        try:
            me = call_api("/auth/me", token=token) or {}
        except RuntimeError:
            pass
        companies = _try_api("/companies")
        cameras = _try_api("/cameras")
        streams = _try_api("/stream-paths")
        vehicles = _try_api("/vehicles")
        drones = _try_api("/drones")

    db_cameras, db_camera_items_error = fetch_db_camera_rows()
    if db_cameras:
        cameras = db_cameras

    stream_by_resource: dict[str, dict[str, Any]] = {}
    for item in streams:
        resource_id = str(item.get("resource_id") or "")
        if not resource_id:
            continue
        path = _text(item.get("path") or item.get("mediamtx_path"))
        is_inference = path.upper().rstrip("/").endswith("/INFERENCE")
        current = stream_by_resource.get(resource_id)
        current_path = _text((current or {}).get("path") or (current or {}).get("mediamtx_path"))
        current_is_inference = current_path.upper().rstrip("/").endswith("/INFERENCE")
        if current is None or (current_is_inference and not is_inference):
            stream_by_resource[resource_id] = item

    try:
        stream_configs = call_api("/stream-configs", token=token) if token else []
    except RuntimeError:
        stream_configs = []

    stream_by_drone = stream_config_mapper.by_drone(stream_configs or [])

    try:
        companies_map, users_map = display_maps(token) if token else ({}, {})
    except RuntimeError:
        companies_map, users_map = {}, {}

    vehicle_items = [normalize_vehicle_item(v, companies_map, users_map) for v in vehicles]
    drone_items = [normalize_drone_item(d, stream_by_drone.get(str(d.get("id"))), companies_map, users_map) for d in drones]
    camera_items = [normalize_camera_item(c, stream_by_resource.get(str(c.get("id")))) for c in cameras]
    camera_items.extend(drone_camera_item(d) for d in drone_items)

    default_camera = camera_items[0] if camera_items else None
    devices = [device_from_camera(item) for item in camera_items]

    camera_by_vehicle: dict[str, dict[str, Any]] = {}
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
        device_from_vehicle(
            item,
            camera_by_vehicle.get(_text(item.get("source_id") or item.get("registration_id"))),
        )
        for item in vehicle_items + drone_items
    )

    username = _text(me.get("username"), "robiotec")
    user_roles = set(me.get("roles") or ["master"])
    role = ", ".join(user_roles)
    is_admin = bool(user_roles.intersection({"master", "admin"}))
    db_codes, db_codes_error = fetch_db_camera_unique_codes()
    db_names, db_names_error = fetch_db_camera_names()
    notif = load_notification_settings()
    email_recipients = notif.get("email", {}).get("recipients") or []
    telegram_chat_ids = notif.get("telegram", {}).get("chat_ids") or []
    public_notif = json.loads(_json(notif))
    if isinstance(public_notif.get("telegram"), dict):
        public_notif["telegram"]["bot_token"] = ""

    return {
        "__AUTH_USERNAME__": username,
        "__DEVELOPER_MENU_LINK__": (
            '<a class="sidebar-link" href="/usuarios"><span class="sidebar-icon">◎</span>'
            '<span class="sidebar-link-copy"><strong>Usuarios</strong><span>Roles y accesos</span></span>'
            '<span class="sidebar-link-tooltip">Usuarios</span></a>'
            '<a class="sidebar-link" href="/registros"><span class="sidebar-icon">▦</span>'
            '<span class="sidebar-link-copy"><strong>Registros</strong><span>Empresas y permisos</span></span>'
            '<span class="sidebar-link-tooltip">Registros</span></a>'
        ),
        "__STATIC_ASSET_VERSION__": str(int(time.time())),
        "__CAMERA_ITEMS_JSON__": _json(camera_items),
        "__DEVICE_CATALOG_JSON__": _json(devices),
        "__DEFAULT_CAMERA_JSON__": _json(default_camera),
        "__TELEMETRY_REFRESH_MS__": "1000",
        "__ERROR_BLOCK__": "",
        "__CAMERA_STREAMS__": "",
        "__CAMERA_SWITCHER_FALLBACK__": camera_switcher_fallback(camera_items),
        "__INFERENCE_TOOLBAR_HIDDEN__": "" if is_admin else "hidden",
        "__USER_IS_ADMIN__": "true" if is_admin else "false",
        "__CAMERA_PAGE_ACTION__": '<button class="camera-register-open" id="camera-register-open" type="button">Registrar cámara</button>',
        "__CAMERA_ADMIN_MODAL__": template_source("partials/camera_admin_modal.html"),
        "__CAMERA_ADMIN_ACCESS_NOTE__": "",
        "__PLATE_PREVIEW_CHOICES__": "",
        "__PLATE_PREVIEW_SELECTED__": "",
        "__WEB_APP_CONFIG__": "{}",
        "__TELEMETRY_FOCUS_RAIL__": template_source("partials/telemetry_focus_rail.html"),
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
        "__HOME_CAMERA_OPTION_ITEMS__": camera_unique_code_options_html(db_codes),
        "__HOME_CAMERA_CODES_JSON__": _json(db_codes),
        "__HOME_CAMERA_NAME_OPTION_ITEMS__": camera_unique_code_options_html(db_names),
        "__HOME_CAMERA_NAMES_JSON__": _json(db_names),
        "__HOME_CAMERA_STATUS__": (
            db_codes_error or db_camera_items_error or f"{len(db_codes)} IDs únicos cargados desde PostgreSQL"
        ),
        "__HOME_CAMERA_NAME_STATUS__": (
            db_names_error or db_camera_items_error or f"{len(db_names)} nombres cargados desde PostgreSQL"
        ),
        "__NOTIFICATION_SETTINGS_JSON__": _json(public_notif),
        "__NOTIFICATION_EMAIL_COUNT__": str(len(email_recipients)),
        "__NOTIFICATION_EMAIL_ROWS__": notification_email_rows_html(email_recipients),
        "__NOTIFICATION_TELEGRAM_CHAT_ID_COUNT__": str(len(telegram_chat_ids)),
        "__NOTIFICATION_TELEGRAM_CHAT_ID_ROWS__": notification_telegram_rows_html(telegram_chat_ids),
        "__NOTIFICATION_TELEGRAM_TOKEN__": "",
        "__USER_ADMIN_ACCESS_NOTE__": "",
        "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "",
        "__USER_ADMIN_MODE_LABEL__": "Master",
        "__USER_ADMIN_SCOPE_LABEL__": "Global",
        "__USER_ADMIN_SCOPE_ROLE__": role,
        "__ROLE_ADMIN_HERO_CARD__": template_source("partials/user_admin_role_hero_card.html") if is_admin else "",
        "__ROLE_ADMIN_SECTION__": template_source("partials/user_admin_role_section.html") if is_admin else "",
    }


# ---------------------------------------------------------------------------
# Renderizado de páginas
# ---------------------------------------------------------------------------

def render_page(request: Request, template: str) -> HTMLResponse | RedirectResponse:
    token = get_token(request)
    if template != "login.html":
        if not token:
            return RedirectResponse("/login")
        try:
            call_api("/auth/me", token=token)
        except RuntimeError as exc:
            if is_auth_error(exc):
                response = RedirectResponse("/login")
                response.delete_cookie(SESSION_COOKIE)
                return response
            raise
    context = build_context(request)
    source = template_renderer.render_source(template, context)
    return HTMLResponse(source)
