"""Router de vehículos y drones."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from back.app.context import (
    _text,
    auth_json_response,
    call_api,
    companies_for_options,
    display_maps,
    ensure_company,
    generated_device_id,
    get_token,
    is_auth_error,
    normalize_drone_item,
    normalize_vehicle_item,
    resolve_source_id,
)
from back.app.state import empresa_mapper, rbox_mapper, settings, stream_config_mapper

router = APIRouter(prefix="/api", tags=["vehicles"])


@router.get("/vehicle-form-options")
def vehicle_form_options(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies = companies_for_options(token)
        users = call_api("/users", token=token) or []
        from back.app.routers.cameras import cameras_registry
        cameras = cameras_registry(request)
    except RuntimeError as exc:
        if is_auth_error(exc):
            return auth_json_response()
        raise
    if isinstance(cameras, JSONResponse):
        return cameras
    return {
        "organizations": [empresa_mapper.item(c) for c in companies],
        "owners": [{"id": int(_text(u.get("id")) or 0), "source_id": u.get("id"), "nombre_usuario": u.get("username"), "username": u.get("username")} for u in users],
        "vehicle_types": [
            {"id": 1, "codigo": "drone_robiotec", "nombre": "Dron Robiotec", "categoria": "dron"},
            {"id": 2, "codigo": "drone_dji", "nombre": "Dron DJI", "categoria": "dron"},
            {"id": 3, "codigo": "auto", "nombre": "Vehículo terrestre", "categoria": "vehiculo"},
        ],
        "cameras": cameras,
        "api_defaults": {"default_drone_device_id": "drone"},
    }


@router.get("/vehicle-registry")
def vehicle_registry(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        companies, users = display_maps(token)
        vehicles = [normalize_vehicle_item(v, companies, users) for v in (call_api("/vehicles", token=token) or [])]
        stream_configs = call_api("/stream-configs", token=token) or []
        stream_by_drone = stream_config_mapper.by_drone(stream_configs)
        drones = [
            normalize_drone_item(d, stream_by_drone.get(str(d.get("id"))), companies, users)
            for d in (call_api("/drones", token=token) or [])
        ]
    except RuntimeError as exc:
        if is_auth_error(exc):
            return auth_json_response()
        raise
    return vehicles + drones


@router.post("/vehicle-registry")
async def vehicle_create(request: Request):
    token = get_token(request)
    p = await request.json()
    companies = companies_for_options(token)
    users = call_api("/users", token=token) or []
    company_id = resolve_source_id(companies, p.get("organizacion_id")) or ensure_company(token)["id"]
    owner_user_id = resolve_source_id(users, p.get("propietario_usuario_id"))
    vehicle_type = _text(p.get("vehicle_type") or p.get("vehicle_type_code"), "auto")
    is_drone = vehicle_type.startswith("drone")
    label = _text(p.get("label"), "Unidad")
    provided_identifier = _text(p.get("identifier"))
    if vehicle_type == "drone_dji":
        identifier = provided_identifier or generated_device_id("DJI")
    elif vehicle_type == "drone_robiotec":
        identifier = provided_identifier or generated_device_id("DRN")
    else:
        identifier = provided_identifier or generated_device_id("CAR")

    if is_drone:
        drone = call_api(
            "/drones", method="POST", token=token,
            data={
                "company_id": company_id,
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
            call_api("/stream-paths", method="POST", token=token,
                     data=stream_config_mapper.drone_stream_path_payload(company_id, drone["id"], path))
        except RuntimeError:
            pass
        rtmp_url = (f"rtmp://{settings.public_host}:{settings.mediamtx_rtmp_port}/{identifier}"
                    if vehicle_type == "drone_dji" else "")
        companies_map, users_map = display_maps(token)
        return JSONResponse(
            {"vehicle": normalize_drone_item(drone, {"origin_url": rtmp_url, "mediamtx_path": path}, companies_map, users_map)},
            status_code=201,
        )
    vehicle = call_api(
        "/vehicles", method="POST", token=token,
        data={
            "company_id": company_id,
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
    companies_map, users_map = display_maps(token)
    return JSONResponse({"vehicle": normalize_vehicle_item(vehicle, companies_map, users_map)}, status_code=201)


@router.put("/vehicle-registry/{registration_id}")
async def vehicle_update(registration_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    p = await request.json()
    companies = companies_for_options(token)
    users = call_api("/users", token=token) or []
    company_id = resolve_source_id(companies, p.get("organizacion_id"))
    owner_user_id = resolve_source_id(users, p.get("propietario_usuario_id"))
    label = _text(p.get("label"), "Unidad")
    vehicle_type = _text(p.get("vehicle_type") or p.get("vehicle_type_code"), "auto")
    is_drone = vehicle_type.startswith("drone")
    if is_drone:
        data: dict[str, Any] = {
            "name": label,
            "provider": "dji" if vehicle_type == "drone_dji" else "robiotec",
            "drone_type": "dji" if vehicle_type == "drone_dji" else "robiotec",
            "manufacturer": "DJI" if vehicle_type == "drone_dji" else "Robiotec",
            "model": _text(p.get("model") or p.get("modelo")) or None,
            "active": True, "can_publish": True,
        }
        if company_id:
            data["company_id"] = company_id
        if owner_user_id:
            data["owner_user_id"] = owner_user_id
        if vehicle_type == "drone_dji":
            data["public_ip"] = settings.public_host
            data["rtmp_port"] = settings.mediamtx_rtmp_port
        drone = call_api(f"/drones/{registration_id}", method="PUT", token=token, data=data)
        stream_configs = call_api("/stream-configs", token=token) or []
        stream_by_drone = stream_config_mapper.by_drone(stream_configs)
        companies_map, users_map = display_maps(token)
        return JSONResponse({"vehicle": normalize_drone_item(drone, stream_by_drone.get(str(drone.get("id"))), companies_map, users_map)})
    data = {"name": label, "vehicle_type": "auto", "model": _text(p.get("model") or p.get("modelo")) or None, "active": True, "can_publish": True}
    if company_id:
        data["company_id"] = company_id
    if owner_user_id:
        data["owner_user_id"] = owner_user_id
    vehicle = call_api(f"/vehicles/{registration_id}", method="PUT", token=token, data=data)
    companies_map, users_map = display_maps(token)
    return JSONResponse({"vehicle": normalize_vehicle_item(vehicle, companies_map, users_map)})


@router.delete("/vehicle-registry/{registration_id}")
def vehicle_delete(registration_id: str, request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    try:
        call_api(f"/vehicles/{registration_id}", method="DELETE", token=token)
    except RuntimeError as vehicle_error:
        if "no encontrado" not in str(vehicle_error).lower() and "not found" not in str(vehicle_error).lower():
            raise
        call_api(f"/drones/{registration_id}", method="DELETE", token=token)
    return {"ok": True}
