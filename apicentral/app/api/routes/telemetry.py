from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Drone, DroneTelemetry, Vehicle, VehicleTelemetry
from app.schemas.common import MessageResponse
from app.schemas.telemetry import DroneTelemetryIn, VehicleTelemetryIn

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def _freshness(received_at) -> str:
    if not received_at:
        return "unavailable"
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - received_at).total_seconds()
    if age_seconds <= 10:
        return "fresh"
    if age_seconds <= 60:
        return "stale"
    return "lost"


def _value(data: dict, *keys: str):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return None


def _latest_drone_item(drone: Drone, telemetry: DroneTelemetry | None) -> dict:
    payload = telemetry.payload if telemetry and isinstance(telemetry.payload, dict) else {}
    altitude = telemetry.altitude if telemetry and telemetry.altitude is not None else _value(payload, "altitude", "altitud", "alt")
    speed = telemetry.speed if telemetry and telemetry.speed is not None else _value(payload, "speed", "velocidad")
    battery = telemetry.battery if telemetry and telemetry.battery is not None else _value(payload, "battery", "bateria", "battery_remaining_pct")
    heading = telemetry.heading if telemetry and telemetry.heading is not None else _value(payload, "heading", "rumbo", "yaw_deg")
    return {
        "device_id": drone.unique_code or str(drone.id),
        "display_name": drone.name,
        "device_kind": "vehicle",
        "vehicle_type": "dron",
        "vehicle_type_code": f"drone_{(drone.provider or drone.drone_type or 'robiotec').lower()}",
        "vehicle_source_id": str(drone.id),
        "lat": telemetry.latitude if telemetry else None,
        "lon": telemetry.longitude if telemetry else None,
        "altitude": altitude,
        "speed": speed,
        "battery": battery,
        "heading": heading,
        "state": telemetry.armed_state if telemetry else None,
        "timestamp": telemetry.received_at if telemetry else None,
        "received_at": telemetry.received_at if telemetry else None,
        "freshness": _freshness(telemetry.received_at if telemetry else None),
        "has_live_telemetry": telemetry is not None,
        "extra": {
            **payload,
            "api_device_id": drone.unique_code or str(drone.id),
            "gps_api_id": drone.unique_code or str(drone.id),
            "battery_remaining_pct": battery if battery is not None else payload.get("battery_remaining_pct"),
            "armed": payload.get("armed"),
            "armed_state": telemetry.armed_state if telemetry else payload.get("armed_state"),
            "yaw_deg": heading if heading is not None else payload.get("yaw_deg"),
        },
    }


def _latest_vehicle_item(vehicle: Vehicle, telemetry: VehicleTelemetry | None) -> dict:
    payload = telemetry.payload if telemetry and isinstance(telemetry.payload, dict) else {}
    speed = telemetry.speed if telemetry and telemetry.speed is not None else _value(payload, "speed", "velocidad")
    heading = telemetry.heading if telemetry and telemetry.heading is not None else _value(payload, "heading", "rumbo", "yaw_deg")
    return {
        "device_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
        "display_name": vehicle.name,
        "device_kind": "vehicle",
        "vehicle_type": "automovil",
        "vehicle_type_code": vehicle.vehicle_type,
        "vehicle_source_id": str(vehicle.id),
        "lat": telemetry.latitude if telemetry else None,
        "lon": telemetry.longitude if telemetry else None,
        "speed": speed,
        "heading": heading,
        "timestamp": telemetry.received_at if telemetry else None,
        "received_at": telemetry.received_at if telemetry else None,
        "freshness": _freshness(telemetry.received_at if telemetry else None),
        "has_live_telemetry": telemetry is not None,
        "extra": {
            **payload,
            "api_device_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
            "gps_api_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
            "yaw_deg": heading if heading is not None else payload.get("yaw_deg"),
        },
    }


@router.post("/drone", response_model=MessageResponse)
def drone_telemetry(payload: DroneTelemetryIn, db: Session = Depends(get_db)) -> MessageResponse:
    data = payload.payload or {}
    db.add(
        DroneTelemetry(
            drone_id=payload.drone_id,
            latitude=_value(data, "latitude", "latitud", "lat"),
            longitude=_value(data, "longitude", "longitud", "lon"),
            altitude=_value(data, "altitude", "altitud", "alt"),
            speed=_value(data, "speed", "velocidad"),
            battery=_value(data, "battery", "bateria", "battery_remaining_pct"),
            heading=_value(data, "heading", "rumbo", "yaw_deg"),
            armed_state=_value(data, "armed_state", "estado_armado"),
            payload=data,
        )
    )
    db.commit()
    return MessageResponse(message="Telemetria de dron recibida")


@router.post("/vehicle", response_model=MessageResponse)
def vehicle_telemetry(payload: VehicleTelemetryIn, db: Session = Depends(get_db)) -> MessageResponse:
    data = payload.payload or {}
    db.add(
        VehicleTelemetry(
            vehicle_id=payload.vehicle_id,
            latitude=_value(data, "latitude", "latitud", "lat"),
            longitude=_value(data, "longitude", "longitud", "lon"),
            speed=_value(data, "speed", "velocidad"),
            heading=_value(data, "heading", "rumbo", "yaw_deg"),
            payload=data,
        )
    )
    db.commit()
    return MessageResponse(message="Telemetria de vehiculo recibida")


@router.get("/latest")
def latest_telemetry(db: Session = Depends(get_db)) -> list[dict]:
    items = []
    for drone in db.scalars(select(Drone).where(Drone.active.is_(True))).all():
        telemetry = db.scalar(
            select(DroneTelemetry)
            .where(DroneTelemetry.drone_id == drone.id)
            .order_by(DroneTelemetry.received_at.desc())
            .limit(1)
        )
        items.append(_latest_drone_item(drone, telemetry))

    for vehicle in db.scalars(select(Vehicle).where(Vehicle.active.is_(True))).all():
        telemetry = db.scalar(
            select(VehicleTelemetry)
            .where(VehicleTelemetry.vehicle_id == vehicle.id)
            .order_by(VehicleTelemetry.received_at.desc())
            .limit(1)
        )
        items.append(_latest_vehicle_item(vehicle, telemetry))

    return items


def _store_device_telemetry(device_id: str, payload: dict, db: Session) -> MessageResponse:
    data = payload or {}
    vehicle = db.scalar(select(Vehicle).where(Vehicle.unique_code == device_id))
    if vehicle:
        db.add(
            VehicleTelemetry(
                vehicle_id=vehicle.id,
                latitude=_value(data, "latitude", "latitud", "lat"),
                longitude=_value(data, "longitude", "longitud", "lon"),
                speed=_value(data, "speed", "velocidad"),
                heading=_value(data, "heading", "rumbo", "yaw_deg"),
                payload=data,
            )
        )
        db.commit()
        return MessageResponse(message="Telemetria de vehiculo recibida por ID API")

    drone = db.scalar(select(Drone).where(Drone.unique_code == device_id))
    if drone:
        db.add(
            DroneTelemetry(
                drone_id=drone.id,
                latitude=_value(data, "latitude", "latitud", "lat"),
                longitude=_value(data, "longitude", "longitud", "lon"),
                altitude=_value(data, "altitude", "altitud", "alt"),
                speed=_value(data, "speed", "velocidad"),
                battery=_value(data, "battery", "bateria", "battery_remaining_pct"),
                heading=_value(data, "heading", "rumbo", "yaw_deg"),
                armed_state=_value(data, "armed_state", "estado_armado"),
                payload=data,
            )
        )
        db.commit()
        return MessageResponse(message="Telemetria de dron recibida por ID API")

    return MessageResponse(message="ID API no registrado")


@router.post("/{device_id}", response_model=MessageResponse)
def device_telemetry(device_id: str, payload: dict, db: Session = Depends(get_db)) -> MessageResponse:
    return _store_device_telemetry(device_id, payload, db)


@router.post("/{device_id}/gps", response_model=MessageResponse)
def device_gps_telemetry(device_id: str, payload: dict, db: Session = Depends(get_db)) -> MessageResponse:
    return _store_device_telemetry(device_id, payload, db)
