"""Router de vehículos y drones."""
from __future__ import annotations

import concurrent.futures
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from back.app.context import (
    _num_id,
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
    require_admin_request,
    resolve_source_id,
)
from back.app.state import empresa_mapper, rbox_mapper, settings, stream_config_mapper

router = APIRouter(prefix="/api", tags=["vehicles"])


def _vehicle_plate_key(value: Any) -> str:
    return _text(value).strip().upper()


def _plate_conflicts_in_company(
    token: str,
    *,
    vehicle_id: str,
    company_id: str | None,
    plate: str | None,
) -> bool:
    plate_key = _vehicle_plate_key(plate)
    if not token or not company_id or not plate_key:
        return False
    try:
        vehicles = call_api("/vehicles", token=token) or []
    except RuntimeError:
        return False
    for vehicle in vehicles:
        if str(vehicle.get("id")) == str(vehicle_id):
            continue
        if str(vehicle.get("company_id") or "") != str(company_id):
            continue
        if _vehicle_plate_key(vehicle.get("plate")) == plate_key:
            return True
    return False


@router.get("/vehicle-form-options")
def vehicle_form_options(request: Request):
    require_admin_request(request)
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
        "owners": [
            {
                "id": _num_id(u.get("id")),
                "source_id": u.get("id"),
                "nombre_usuario": u.get("username"),
                "username": u.get("username"),
                "display_name": u.get("name") or u.get("email") or u.get("username"),
                "company_id": str(u.get("company_id")) if u.get("company_id") else None,
                "organizacion_source_id": str(u.get("company_id")) if u.get("company_id") else None,
                "organizacion_id": _num_id(u.get("company_id")) if u.get("company_id") else None,
            }
            for u in users
        ],
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            companies_future = executor.submit(companies_for_options, token)
            vehicles_future = executor.submit(call_api, "/vehicles", token=token)
            streams_future = executor.submit(call_api, "/stream-configs", token=token)
            drones_future = executor.submit(call_api, "/drones", token=token)
            companies_payload = companies_future.result() or []
            try:
                stream_configs = streams_future.result() or []
            except RuntimeError:
                stream_configs = []
            try:
                users_payload = call_api("/users", token=token) or []
            except RuntimeError:
                users_payload = []
            vehicles_payload = vehicles_future.result() or []
            drones_payload = drones_future.result() or []
        companies = {str(item.get("id")): item for item in companies_payload}
        users = {str(item.get("id")): item for item in users_payload}
        vehicles = [normalize_vehicle_item(v, companies, users) for v in vehicles_payload]
        stream_by_drone = stream_config_mapper.by_drone(stream_configs)
        drones = [
            normalize_drone_item(d, stream_by_drone.get(str(d.get("id"))), companies, users)
            for d in drones_payload
        ]
    except RuntimeError as exc:
        if is_auth_error(exc):
            return auth_json_response()
        raise
    return vehicles + drones


@router.post("/vehicle-registry")
async def vehicle_create(request: Request):
    require_admin_request(request)
    token = get_token(request)
    p = await request.json()
    companies = companies_for_options(token)
    users = call_api("/users", token=token) or []
    company_id = resolve_source_id(companies, p.get("organizacion_id")) or ensure_company(token)["id"]
    owner_user_id = resolve_source_id(users, p.get("propietario_usuario_id"))
    vehicle_type = _text(p.get("vehicle_type") or p.get("vehicle_type_code"), "auto")
    is_drone = vehicle_type.startswith("drone")
    label = _text(p.get("label"), "Unidad")
    driver_name = _text(p.get("driver_name") or p.get("chofer")) or None
    vehicle_subtype = None if is_drone else (_text(p.get("vehicle_subtype") or p.get("tipo_automovil_codigo")) or None)
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
            "vehicle_subtype": vehicle_subtype,
            "unique_code": identifier,
            "plate": identifier,
            "model": _text(p.get("model") or p.get("modelo")) or None,
            "driver_name": driver_name,
            "active": True,
            "can_publish": True,
        },
    )
    companies_map, users_map = display_maps(token)
    return JSONResponse({"vehicle": normalize_vehicle_item(vehicle, companies_map, users_map)}, status_code=201)


@router.put("/vehicle-registry/{registration_id}")
async def vehicle_update(registration_id: str, request: Request):
    require_admin_request(request)
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
    driver_name = _text(p.get("driver_name") or p.get("chofer")) or None
    is_drone = vehicle_type.startswith("drone")
    vehicle_subtype = None if is_drone else (_text(p.get("vehicle_subtype") or p.get("tipo_automovil_codigo")) or None)
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
    data = {
        "name": label,
        "vehicle_type": vehicle_type,
        "vehicle_subtype": vehicle_subtype,
        "model": _text(p.get("model") or p.get("modelo")) or None,
        "driver_name": driver_name,
        "active": True,
        "can_publish": True,
    }
    if company_id:
        data["company_id"] = company_id
    if owner_user_id:
        data["owner_user_id"] = owner_user_id
    if company_id:
        try:
            current_vehicle = call_api(f"/vehicles/{registration_id}", token=token) or {}
        except RuntimeError:
            current_vehicle = {}
        if _plate_conflicts_in_company(
            token,
            vehicle_id=registration_id,
            company_id=company_id,
            plate=current_vehicle.get("plate"),
        ):
            data["plate"] = None
    vehicle = call_api(f"/vehicles/{registration_id}", method="PUT", token=token, data=data)
    companies_map, users_map = display_maps(token)
    return JSONResponse({"vehicle": normalize_vehicle_item(vehicle, companies_map, users_map)})


@router.delete("/vehicle-registry/{registration_id}")
def vehicle_delete(registration_id: str, request: Request):
    require_admin_request(request)
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
