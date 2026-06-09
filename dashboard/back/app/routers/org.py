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
)
from back.app.state import empresa_mapper, vehicle_telemetry_mapper

router = APIRouter(prefix="/api", tags=["org"])


@router.get("/organizations")
def organizations(request: Request):
    token = get_token(request)
    from back.app.context import companies_for_options
    return [empresa_mapper.item(c) for c in companies_for_options(token)]


@router.get("/users")
def users(request: Request):
    token = get_token(request)
    return [
        {"id": _num_id(u.get("id")), "source_id": u.get("id"), "nombre_usuario": u.get("username"),
         "email": u.get("email"), "activo": u.get("active")}
        for u in (call_api("/users", token=token) or [])
    ]


@router.get("/user-role-options")
def user_role_options():
    roles = ["master", "company_admin", "area_admin", "operator", "viewer"]
    return {"roles": [{"id": i + 1, "codigo": role, "nombre": role} for i, role in enumerate(roles)]}


@router.get("/user-roles")
def user_roles():
    return user_role_options()["roles"]


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
