"""Router de organizaciones, usuarios, telemetría y catálogo de dispositivos."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from back.app.context import (
    _num_id,
    _text,
    build_context,
    call_api,
    get_token,
    merge_live_telemetry,
    require_admin_role,
    resolve_source_id,
    companies_for_options,
)
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
    if not require_admin_role(token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    p = await request.json()
    name = _text(p.get("nombre")).strip()
    if not name:
        return JSONResponse({"error": "nombre_requerido"}, status_code=400)
    active = p.get("activa", True)
    if isinstance(active, str):
        active = active.lower() != "false"
    try:
        company = call_api("/companies", method="POST", token=token, data={"name": name, "active": active})
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
    if not require_admin_role(token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    companies = companies_for_options(token)
    source_id = resolve_source_id(companies, org_id)
    if not source_id:
        return JSONResponse({"error": "organization_not_found"}, status_code=404)
    p = await request.json()
    name = _text(p.get("nombre")).strip()
    if not name:
        return JSONResponse({"error": "nombre_requerido"}, status_code=400)
    active = p.get("activa", True)
    if isinstance(active, str):
        active = active.lower() != "false"
    try:
        company = call_api(f"/companies/{source_id}", method="PUT", token=token, data={"name": name, "active": active})
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
    if not require_admin_role(token):
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
        raw = call_api("/roles", token=token) or []
    except RuntimeError:
        return []
    return [
        {"id": r.get("id"), "codigo": r.get("name"), "nombre": r.get("name")}
        for r in raw if r.get("active") and not r.get("deleted_at")
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
