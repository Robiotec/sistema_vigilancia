"""Router de organizaciones, usuarios, telemetría y catálogo de dispositivos."""
from __future__ import annotations

import csv
import io
import json
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from back.app.context import (
    _num_id,
    _text,
    build_context,
    call_api,
    get_token,
    merge_live_telemetry,
    require_admin_role,
    require_master_role,
    resolve_source_id,
    companies_for_options,
)
from back.app.services.db_pool import fetch_all
from back.app.state import empresa_mapper, vehicle_telemetry_mapper

router = APIRouter(prefix="/api", tags=["org"])


@router.get("/organizations")
def organizations(request: Request):
    token = get_token(request)
    try:
        return [empresa_mapper.item(c) for c in companies_for_options(token)]
    except RuntimeError:
        return []


@router.post("/organizations")
async def organization_create(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    if not require_master_role(token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    p = await request.json()
    name = _text(p.get("nombre")).strip()
    description = _text(p.get("descripcion")).strip()
    if not name:
        return JSONResponse({"error": "nombre_requerido"}, status_code=400)
    active = p.get("activa", True)
    if isinstance(active, str):
        active = active.lower() != "false"
    try:
        company = call_api(
            "/companies",
            method="POST",
            token=token,
            data={"name": name, "address": description or None, "active": active},
        )
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "unique" in msg or "already" in msg or "duplicat" in msg:
            return JSONResponse({"error": "nombre_duplicado"}, status_code=409)
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"organization": empresa_mapper.item(company)}, status_code=201)


@router.put("/organizations/{org_id}")
async def organization_update(org_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    if not require_master_role(token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    companies = companies_for_options(token)
    source_id = resolve_source_id(companies, org_id)
    if not source_id:
        return JSONResponse({"error": "organization_not_found"}, status_code=404)
    p = await request.json()
    name = _text(p.get("nombre")).strip()
    description = _text(p.get("descripcion")).strip()
    if not name:
        return JSONResponse({"error": "nombre_requerido"}, status_code=400)
    active = p.get("activa", True)
    if isinstance(active, str):
        active = active.lower() != "false"
    try:
        company = call_api(
            f"/companies/{source_id}",
            method="PUT",
            token=token,
            data={"name": name, "address": description or None, "active": active},
        )
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "unique" in msg or "already" in msg or "duplicat" in msg:
            return JSONResponse({"error": "nombre_duplicado"}, status_code=409)
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"organization": empresa_mapper.item(company)})


@router.delete("/organizations/{org_id}")
def organization_delete(org_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    if not require_master_role(token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    companies = companies_for_options(token)
    source_id = resolve_source_id(companies, org_id)
    if not source_id:
        return JSONResponse({"error": "organization_not_found"}, status_code=404)
    try:
        call_api(f"/companies/{source_id}", method="DELETE", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True})


def _format_user(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "username": u.get("username"),
        "name": u.get("name"),
        "email": u.get("email"),
        "active": u.get("active"),
        "company_id": str(u["company_id"]) if u.get("company_id") else None,
        "role_names": u.get("role_names") or u.get("roles") or [],
    }


@router.get("/users")
def users(request: Request):
    token = get_token(request)
    if not token:
        return []
    if not require_admin_role(token):
        me = call_api("/auth/me", token=token) or {}
        return [_format_user(me)] if me.get("id") else []
    try:
        return [_format_user(u) for u in (call_api("/users", token=token) or [])]
    except RuntimeError:
        return []


@router.put("/users/{user_id}")
async def update_user(user_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = await request.json()
    if not require_admin_role(token):
        me = call_api("/auth/me", token=token) or {}
        if str(me.get("id")) != user_id:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        profile_payload = {
            "name": payload.get("name"),
            "email": payload.get("email"),
            "new_password": payload.get("password") or None,
        }
        try:
            result = call_api("/auth/me", method="PUT", token=token, data=profile_payload)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(_format_user({**result, "role_names": result.get("roles", [])}))
    try:
        result = call_api(f"/users/{user_id}", method="PUT", token=token, data=payload)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


@router.get("/user-role-options")
def user_role_options(request: Request):
    token = get_token(request)
    if not token:
        return []
    try:
        me = call_api("/auth/me", token=token) or {}
    except RuntimeError:
        return []
    my_roles = set(me.get("roles") or [])
    try:
        raw = call_api("/roles", token=token) or []
    except RuntimeError:
        return []
    if "master" in my_roles:
        allowed = None
    elif "admin" in my_roles:
        allowed = {"operator_cameras", "operator_map", "viewer"}
    else:
        allowed = set()
    labels = {
        "master": "Master ROBIOTEC",
        "admin": "Administrador de organización",
        "operator_cameras": "Operador solo cámaras",
        "operator_map": "Operador solo mapa de carros",
        "viewer": "Visor sin edición",
    }
    supported = set(labels)
    return [
        {"id": r.get("id"), "codigo": r.get("name"), "nombre": labels.get(r.get("name"), r.get("name"))}
        for r in raw
        if (
            r.get("active")
            and not r.get("deleted_at")
            and r.get("name") in supported
            and (allowed is None or r.get("name") in allowed)
        )
    ]


@router.get("/user-roles")
def user_roles(request: Request):
    return user_role_options(request)


@router.get("/devices")
def devices(request: Request):
    return JSONResponse(json.loads(build_context(request)["__DEVICE_CATALOG_JSON__"]))


@router.get("/telemetry")
def telemetry(request: Request):
    token = get_token(request)
    device_list = json.loads(build_context(request)["__DEVICE_CATALOG_JSON__"])
    base_items = [item for item in (vehicle_telemetry_mapper.inventory_item(d) for d in device_list) if item]
    try:
        live_items = call_api("/telemetry/latest", token=token) or []
    except RuntimeError:
        live_items = []
    return merge_live_telemetry(base_items, live_items if isinstance(live_items, list) else [])


@router.get("/telemetry/history")
def telemetry_history(request: Request):
    """Historial de posiciones de un vehículo para un día (proxy a API Central)."""
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    params = dict(request.query_params)
    # Mapear device_id → vehicle_id usando catálogo
    device_id = params.pop("device_id", None)
    vehicle_ids = _resolve_vehicle_ids(request, device_id) if device_id else [_text(params.get("vehicle_id"))]
    vehicle_ids = [item for item in dict.fromkeys(vehicle_ids) if item]
    if not vehicle_ids:
        return JSONResponse({"error": "Se requiere device_id o vehicle_id"}, status_code=400)
    errors: list[str] = []
    results: list[dict] = []
    for vehicle_id in vehicle_ids:
        params["vehicle_id"] = vehicle_id
        try:
            result = call_api(f"/telemetry/history?{urlencode(params)}", token=token)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(result, list):
            results.extend(item for item in result if isinstance(item, dict))
    if results:
        return _merge_history_points(results)
    if errors and len(errors) == len(vehicle_ids):
        return JSONResponse({"error": errors[0]}, status_code=502)
    return []


@router.get("/telemetry/km-summary")
def telemetry_km_summary(request: Request):
    """Resumen de km por día para un rango (proxy a API Central)."""
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    params = dict(request.query_params)
    device_id = params.pop("device_id", None)
    vehicle_id = _resolve_vehicle_id(request, device_id) if device_id else params.get("vehicle_id")
    if not vehicle_id:
        return JSONResponse({"error": "Se requiere device_id o vehicle_id"}, status_code=400)
    params["vehicle_id"] = vehicle_id
    try:
        result = call_api(f"/telemetry/km-summary?{urlencode(params)}", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return result or []


@router.get("/telemetry/km-summary/export")
def telemetry_km_summary_export(request: Request):
    """Exporta resumen de km como CSV."""
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    params = dict(request.query_params)
    device_id = params.pop("device_id", None)
    label = params.pop("label", device_id or "vehiculo")
    vehicle_id = _resolve_vehicle_id(request, device_id) if device_id else params.get("vehicle_id")
    if not vehicle_id:
        return JSONResponse({"error": "Se requiere device_id"}, status_code=400)
    params["vehicle_id"] = vehicle_id
    try:
        rows = call_api(f"/telemetry/km-summary?{urlencode(params)}", token=token) or []
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Vehículo", "Fecha", "Km recorridos", "Encendido ON", "Encendido OFF"])
    total_km = 0.0
    for r in rows:
        km = round(float(r.get("km", 0)), 3)
        total_km += km
        writer.writerow([
            label,
            r.get("date", ""),
            f"{km:.3f}",
            r.get("ignition_on", 0),
            r.get("ignition_off", 0),
        ])
    writer.writerow(["", "TOTAL", f"{total_km:.3f}", "", ""])

    buf.seek(0)
    filename = f"km_{label.replace(' ', '_')}_{params.get('from_date', 'rango')}_a_{params.get('to_date', '')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/telemetry/km-fleet")
def telemetry_km_fleet(request: Request):
    """Resumen agregado de km para la flota en un rango de fechas."""
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    params = dict(request.query_params)
    if not params.get("from_date") or not params.get("to_date"):
        return JSONResponse({"error": "Se requieren from_date y to_date"}, status_code=400)
    params.setdefault("group_by", "summary")
    try:
        result = call_api(f"/telemetry/km-fleet?{urlencode(params)}", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return result or {"vehicles": [], "daily": [], "monthly": [], "totals": {}}


@router.get("/geofences")
def geofences(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        result = call_api("/telemetry/geofences", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return result or []


@router.post("/geofences")
async def geofence_create(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = await request.json()
    try:
        result = call_api("/telemetry/geofences", method="POST", token=token, data=payload)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result, status_code=201)


@router.put("/geofences/{geofence_id}")
async def geofence_update(geofence_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = await request.json()
    try:
        return call_api(f"/telemetry/geofences/{geofence_id}", method="PUT", token=token, data=payload)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.delete("/geofences/{geofence_id}")
def geofence_delete(geofence_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        return call_api(f"/telemetry/geofences/{geofence_id}", method="DELETE", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/geofence-alerts")
def geofence_alerts(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    query = urlencode(dict(request.query_params))
    suffix = f"?{query}" if query else ""
    try:
        result = call_api(f"/telemetry/geofence-alerts{suffix}", token=token)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return result or []


@router.patch("/geofence-alerts/{alert_id}/processed")
async def geofence_alert_processed(alert_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    payload = await request.json()
    try:
        return call_api(f"/telemetry/geofence-alerts/{alert_id}/processed", method="PATCH", token=token, data=payload)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _resolve_vehicle_id(request: Request, device_id: str) -> str | None:
    """Busca vehicle_id (UUID) a partir del device_id (unique_code/placa) usando el catálogo."""
    ids = _resolve_vehicle_ids(request, device_id)
    return ids[0] if ids else None


def _plate_lookup_key(value: str) -> str:
    text = _text(value).upper()
    if not (re.search(r"[A-Z]", text) and re.search(r"\d", text)):
        return ""
    return re.sub(r"[^A-Z0-9]", "", text)


def _resolve_vehicle_ids_from_db(device_id: str) -> list[str]:
    normalized_device_id = _text(device_id)
    if not normalized_device_id:
        return []
    plate_key = _plate_lookup_key(normalized_device_id)
    try:
        rows = fetch_all(
            """
            SELECT id::text AS id
            FROM vehicles
            WHERE deleted_at IS NULL
              AND (
                id::text = %(raw)s
                OR lower(trim(coalesce(unique_code, ''))) = lower(%(raw)s)
                OR lower(trim(coalesce(plate, ''))) = lower(%(raw)s)
                OR (
                  %(plate_key)s <> ''
                  AND regexp_replace(upper(coalesce(plate, '')), '[^A-Z0-9]', '', 'g') LIKE %(plate_key_like)s
                )
              )
            ORDER BY
              CASE
                WHEN id::text = %(raw)s THEN 0
                WHEN lower(trim(coalesce(unique_code, ''))) = lower(%(raw)s) THEN 1
                WHEN lower(trim(coalesce(plate, ''))) = lower(%(raw)s) THEN 2
                ELSE 3
              END,
              plate NULLS LAST,
              unique_code NULLS LAST
            LIMIT 12
            """,
            {
                "raw": normalized_device_id,
                "plate_key": plate_key,
                "plate_key_like": f"{plate_key}%",
            },
        )
    except Exception:
        return []
    return [_text(row.get("id")) for row in rows or [] if _text(row.get("id"))]


def _resolve_vehicle_ids(request: Request, device_id: str) -> list[str]:
    """Busca vehicle_id(s) a partir de UUID, unique_code, IMEI o placa."""
    normalized_device_id = _text(device_id)
    if not normalized_device_id:
        return []
    resolved: list[str] = []
    try:
        device_list = json.loads(build_context(request)["__DEVICE_CATALOG_JSON__"])
        for d in device_list:
            extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
            vehicle_source_id = _text(
                d.get("vehicle_source_id")
                or d.get("source_id")
                or d.get("vehicle_id")
                or extra.get("vehicle_source_id")
                or extra.get("source_id")
                or extra.get("vehicle_id")
            )
            candidates = {
                vehicle_source_id,
                _text(d.get("device_id")),
                _text(d.get("api_device_id")),
                _text(d.get("unique_code")),
                _text(d.get("plate")),
                _text(d.get("id")),
                _text(extra.get("api_device_id")),
                _text(extra.get("gps_api_id")),
            }
            if normalized_device_id in {item for item in candidates if item}:
                value = vehicle_source_id or (normalized_device_id if len(normalized_device_id) == 36 else "")
                if value:
                    resolved.append(value)
    except Exception:
        pass
    resolved.extend(_resolve_vehicle_ids_from_db(normalized_device_id))
    if len(normalized_device_id) == 36:
        resolved.append(normalized_device_id)
    return [item for item in dict.fromkeys(resolved) if item]


def _history_point_sort_key(point: dict) -> str:
    return _text(point.get("gps_time") or point.get("timestamp") or point.get("received_at"))


def _merge_history_points(points: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict] = []
    for point in sorted(points, key=_history_point_sort_key):
        key = (
            _history_point_sort_key(point),
            _text(point.get("lat")),
            _text(point.get("lon")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(point)
    if merged:
        merged[0]["segment_status"] = "start"
        merged[0]["segment_reason"] = None
        merged[0]["counted_for_km"] = False
    return merged
