import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.entities import (
    Company,
    Drone,
    DroneTelemetry,
    Vehicle,
    VehicleRouteSegment,
    VehicleTelemetry,
)
from app.schemas.common import MessageResponse
from app.schemas.telemetry import DroneTelemetryIn, VehicleTelemetryIn
from app.services.auth_service import get_user_roles
from app.services.fleet import (
    ECUADOR_TZ,
    MAX_REASONABLE_SPEED_KMH,
    MAX_SEGMENT_DISTANCE_KM,
    MAX_SEGMENT_GAP_SECONDS,
    build_route_points,
    build_hybrid_segment,
    coerce_float,
    gps_datetime_from_payload,
    is_valid_coordinate,
    local_date_for_point,
    normalize_vehicle_payload,
    point_in_geofence,
    summarize_daily_mileage,
)
from app.core.config import get_settings

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

_GEOFENCE_TABLES_CACHE_TTL_SECONDS = 30.0
_geofence_tables_cache_at = 0.0
_geofence_tables_cache_value: bool | None = None
_KM_FLEET_CACHE_TTL_SECONDS = 45.0
_KM_FLEET_CACHE_MAX_ITEMS = 128
_km_fleet_cache: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = {}
_km_fleet_cache_lock = threading.Lock()
_RETRYABLE_OSRM_SEGMENT_REASONS = {"osrm_budget_deferred", "osrm_disabled"}


def _freshness(received_at) -> str:
    if not received_at:
        return "unavailable"
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - received_at).total_seconds()
    if age_seconds <= 10:
        return "fresh"
    if age_seconds <= 120:
        return "stale"
    return "lost"


def _value(data: dict, *keys: str):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return None


def _is_master(db: Session, user) -> bool:
    return "master" in set(get_user_roles(db, user))


def _can_view_map(db: Session, user) -> bool:
    return bool(set(get_user_roles(db, user)).intersection({"master", "admin", "viewer", "operator_map"}))


def _assert_map_access(db: Session, user) -> None:
    if not _can_view_map(db, user):
        raise HTTPException(status_code=403, detail="No autorizado para telemetria vehicular")


def _assert_vehicle_scope(db: Session, user, vehicle: Vehicle) -> None:
    if _is_master(db, user):
        return
    if not user.company_id or vehicle.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="Vehiculo fuera de la organizacion")


def _can_manage_fleet(db: Session, user) -> bool:
    return bool(set(get_user_roles(db, user)).intersection({"master", "admin", "operator_map"}))


def _assert_fleet_manage_access(db: Session, user) -> None:
    if not _can_manage_fleet(db, user):
        raise HTTPException(status_code=403, detail="No autorizado para gestionar flota")


def _operational_from_payload(payload: dict[str, Any], freshness: str) -> bool:
    status = str(payload.get("status") or payload.get("operational_status") or "").strip().upper()
    event = str(payload.get("event") or payload.get("report_type") or "").strip().upper()
    status_text = f"{status} {event}"
    if any(flag in status_text for flag in ("NO OPERATIVO", "INOPERATIVO", "FUERA DE SERVICIO", "SIN SEÑAL")):
        return False
    if status == "OPERATIVO":
        return freshness != "lost"
    if payload.get("operational") is False:
        return False
    return freshness in {"fresh", "stale"}


def _operational_status(payload: dict[str, Any], freshness: str) -> str:
    if _operational_from_payload(payload, freshness):
        return str(payload.get("status") or "OPERATIVO")
    if freshness == "lost":
        return "SIN SEÑAL"
    return str(payload.get("status") or "NO OPERATIVO")


def _vehicle_point_values(payload: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
    lat = coerce_float(_value(payload, "latitude", "latitud", "lat"))
    lon = coerce_float(_value(payload, "longitude", "longitud", "lon", "lng"))
    speed = coerce_float(_value(payload, "speed", "velocidad"))
    heading = coerce_float(_value(payload, "heading", "rumbo", "yaw_deg"))
    if not is_valid_coordinate(lat, lon):
        return None, None, speed, heading
    return lat, lon, speed, heading


def _latest_drone_item(drone: Drone, telemetry: DroneTelemetry | None) -> dict:
    payload = telemetry.payload if telemetry and isinstance(telemetry.payload, dict) else {}
    altitude = telemetry.altitude if telemetry and telemetry.altitude is not None else _value(payload, "altitude", "altitud", "alt")
    speed = telemetry.speed if telemetry and telemetry.speed is not None else _value(payload, "speed", "velocidad")
    battery = telemetry.battery if telemetry and telemetry.battery is not None else _value(payload, "battery", "bateria", "battery_remaining_pct")
    heading = telemetry.heading if telemetry and telemetry.heading is not None else _value(payload, "heading", "rumbo", "yaw_deg")
    return {
        "device_id": drone.unique_code or str(drone.id),
        "company_id": str(drone.company_id),
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
            "company_id": str(drone.company_id),
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
    freshness = _freshness(telemetry.received_at if telemetry else None)
    operational = _operational_from_payload(payload, freshness)
    return {
        "device_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
        "company_id": str(vehicle.company_id),
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
        "freshness": freshness,
        "has_live_telemetry": telemetry is not None,
        "operational": operational,
        "operational_status": _operational_status(payload, freshness),
        "extra": {
            **payload,
            "company_id": str(vehicle.company_id),
            "api_device_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
            "gps_api_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
            "vehicle_source_id": str(vehicle.id),
            "operational": operational,
            "operational_status": _operational_status(payload, freshness),
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


def _duplicate_vehicle_point_exists(
    db: Session,
    *,
    vehicle_id: UUID,
    lat: float | None,
    lon: float | None,
    payload: dict[str, Any],
) -> bool:
    if lat is None or lon is None:
        return False
    if str(payload.get("source") or "").lower() != "artemis":
        return False
    gps_raw = str(payload.get("gps_datetime") or "").strip()
    gps_iso = str(payload.get("gps_datetime_iso") or "").strip()
    if not gps_raw and not gps_iso:
        return False
    row = db.execute(
        text(
            """
            SELECT id
            FROM vehicle_telemetry
            WHERE vehicle_id = :vehicle_id
              AND latitude IS NOT DISTINCT FROM :lat
              AND longitude IS NOT DISTINCT FROM :lon
              AND (
                (:gps_raw <> '' AND payload->>'gps_datetime' = :gps_raw)
                OR (:gps_iso <> '' AND payload->>'gps_datetime_iso' = :gps_iso)
              )
            LIMIT 1
            """
        ),
        {"vehicle_id": vehicle_id, "lat": lat, "lon": lon, "gps_raw": gps_raw, "gps_iso": gps_iso},
    ).first()
    return row is not None


def _db_is_postgres(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _geofence_tables_ready(db: Session, *, force: bool = False) -> bool:
    global _geofence_tables_cache_at, _geofence_tables_cache_value
    if not _db_is_postgres(db):
        return False
    now = time.monotonic()
    if (
        not force
        and _geofence_tables_cache_value is not None
        and now - _geofence_tables_cache_at < _GEOFENCE_TABLES_CACHE_TTL_SECONDS
    ):
        return _geofence_tables_cache_value
    ready = bool(
        db.execute(
            text(
                """
                SELECT
                    to_regclass('geofences') IS NOT NULL
                    AND to_regclass('vehicle_geofence_states') IS NOT NULL
                    AND to_regclass('geofence_alerts') IS NOT NULL
                """
            )
        ).scalar()
    )
    _geofence_tables_cache_at = now
    _geofence_tables_cache_value = ready
    return ready


def _assert_geofence_tables_ready(db: Session) -> None:
    if not _geofence_tables_ready(db, force=True):
        raise HTTPException(status_code=503, detail="geofences_not_ready")


def _ensure_route_segment_table(db: Session) -> None:
    try:
        VehicleRouteSegment.__table__.create(bind=db.get_bind(), checkfirst=True)
    except Exception:
        db.rollback()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_dump(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {})


def _bool_from_payload(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "falso", "no", "off", "inactivo"}
    return bool(value)


def _row_value(row: Any, key: str) -> Any:
    if hasattr(row, "get"):
        return row.get(key)
    return getattr(row, key, None)


def _active_geofences_for_vehicle(db: Session, vehicle: Vehicle) -> list[dict[str, Any]]:
    if not _geofence_tables_ready(db):
        return []
    params: dict[str, Any] = {}
    company_clause = ""
    if vehicle.company_id:
        company_clause = "AND company_id = :company_id"
        params["company_id"] = vehicle.company_id
    rows = db.execute(
        text(
            f"""
            SELECT id, name, geofence_type, geometry
            FROM geofences
            WHERE deleted_at IS NULL
              AND active IS TRUE
              {company_clause}
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _point_inside_geofences(point: dict[str, Any], geofences: list[dict[str, Any]]) -> bool:
    lat = coerce_float(point.get("lat"))
    lon = coerce_float(point.get("lon"))
    if lat is None or lon is None:
        return False
    for geofence in geofences:
        if point_in_geofence(lat, lon, str(geofence.get("geofence_type") or ""), _json_object(geofence.get("geometry"))):
            return True
    return False


def _segment_inside_geofences(previous: dict[str, Any], point: dict[str, Any], geofences: list[dict[str, Any]]) -> bool:
    if not geofences:
        return False
    if _point_inside_geofences(previous, geofences) or _point_inside_geofences(point, geofences):
        return True
    mid_lat = (float(previous["lat"]) + float(point["lat"])) / 2
    mid_lon = (float(previous["lon"]) + float(point["lon"])) / 2
    return _point_inside_geofences({"lat": mid_lat, "lon": mid_lon}, geofences)


def _segment_geometry_payload(latlon: list[list[float]]) -> dict[str, Any]:
    return {"type": "LineString", "coordinate_order": "latlon", "coordinates": latlon}


def _segment_geometry_latlon(geometry: Any) -> list[list[float]]:
    payload = _json_object(geometry)
    coordinates = payload.get("coordinates")
    if not isinstance(coordinates, list):
        return []
    result: list[list[float]] = []
    for point in coordinates:
        if not isinstance(point, list) or len(point) < 2:
            continue
        lat = coerce_float(point[0])
        lon = coerce_float(point[1])
        if lat is not None and lon is not None:
            result.append([lat, lon])
    return result


def _apply_segment_to_point(point: dict[str, Any], segment: VehicleRouteSegment | None) -> None:
    if not segment:
        return
    point["segment_status"] = segment.segment_kind
    point["segment_reason"] = segment.segment_reason
    point["distance_km"] = float(segment.distance_km or 0.0)
    point["elapsed_seconds"] = float(segment.elapsed_seconds or 0.0)
    point["implied_speed_kmh"] = float(segment.implied_speed_kmh or 0.0)
    point["counted_for_km"] = segment.segment_kind in {"osrm", "raw"}
    point["segment_geometry"] = _segment_geometry_latlon(segment.geometry)


def _route_segment_can_retry_osrm(segment: VehicleRouteSegment | None) -> bool:
    if not segment:
        return False
    return (
        str(segment.segment_kind or "").lower() == "raw"
        and str(segment.segment_reason or "").lower() in _RETRYABLE_OSRM_SEGMENT_REASONS
    )


def _update_route_segment_row(row: VehicleRouteSegment, segment: dict[str, Any]) -> None:
    row.segment_kind = segment["segment_kind"]
    row.segment_reason = segment.get("segment_reason")
    row.distance_km = float(segment.get("distance_km") or 0.0)
    row.elapsed_seconds = float(segment.get("elapsed_seconds") or 0.0)
    row.implied_speed_kmh = float(segment.get("implied_speed_kmh") or 0.0)
    row.confidence = segment.get("confidence")
    row.geometry = _segment_geometry_payload(segment.get("geometry") or [])


def _materialize_hybrid_route_segments(
    db: Session,
    *,
    vehicle: Vehicle,
    points: list[dict[str, Any]],
    target_day: date,
) -> dict[str, VehicleRouteSegment]:
    _ensure_route_segment_table(db)
    point_ids = [str(point.get("telemetry_id") or "") for point in points if point.get("telemetry_id")]
    if len(point_ids) < 2:
        return {}
    existing_rows = db.scalars(
        select(VehicleRouteSegment).where(
            VehicleRouteSegment.vehicle_id == vehicle.id,
            VehicleRouteSegment.local_day == target_day,
            VehicleRouteSegment.to_telemetry_id.in_(point_ids),
        )
    ).all()
    by_to_id = {str(row.to_telemetry_id): row for row in existing_rows}
    geofences = _active_geofences_for_vehicle(db, vehicle)
    settings = get_settings()
    osrm_base_url = str(settings.osrm_base_url or "").strip()
    osrm_remaining = max(0, int(settings.osrm_max_segments_per_request or 0))
    osrm_deadline = time.monotonic() + max(0.5, float(settings.osrm_request_budget_seconds or 0.0))
    osrm_timeout = max(0.2, min(1.0, float(settings.osrm_request_timeout_seconds or 0.8)))
    changed = False
    for index in range(1, len(points)):
        previous = points[index - 1]
        point = points[index]
        to_id = str(point.get("telemetry_id") or "")
        from_id = str(previous.get("telemetry_id") or "")
        if not to_id or not from_id:
            continue
        existing = by_to_id.get(to_id)
        inside_geofence = _segment_inside_geofences(previous, point, geofences)
        point_status = str(point.get("segment_status") or "normal").lower()
        can_try_osrm = (
            bool(osrm_base_url)
            and osrm_remaining > 0
            and time.monotonic() < osrm_deadline
            and point_status not in {"gap", "suspicious"}
            and not inside_geofence
        )
        if existing and not (_route_segment_can_retry_osrm(existing) and can_try_osrm):
            continue
        segment = build_hybrid_segment(
            previous,
            point,
            inside_geofence=inside_geofence,
            osrm_base_url=osrm_base_url if can_try_osrm else "",
            confidence_min=settings.osrm_match_confidence_min,
            timeout_seconds=osrm_timeout,
        )
        if can_try_osrm:
            osrm_remaining -= 1
        elif segment.get("segment_kind") == "raw" and not inside_geofence:
            segment["segment_reason"] = "osrm_budget_deferred" if osrm_base_url else "osrm_disabled"
        if existing:
            _update_route_segment_row(existing, segment)
            changed = True
            continue
        row = VehicleRouteSegment(
            vehicle_id=vehicle.id,
            from_telemetry_id=from_id,
            to_telemetry_id=to_id,
            local_day=target_day,
            segment_kind=segment["segment_kind"],
            segment_reason=segment.get("segment_reason"),
            distance_km=float(segment.get("distance_km") or 0.0),
            elapsed_seconds=float(segment.get("elapsed_seconds") or 0.0),
            implied_speed_kmh=float(segment.get("implied_speed_kmh") or 0.0),
            confidence=segment.get("confidence"),
            geometry=_segment_geometry_payload(segment.get("geometry") or []),
        )
        db.add(row)
        by_to_id[to_id] = row
        changed = True
    if changed:
        db.commit()
    return by_to_id


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _normalize_geofence_color(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        raw = str(value).strip()
        if not raw:
            continue
        if not raw.startswith("#"):
            raw = f"#{raw}"
        hex_value = raw[1:]
        if len(hex_value) not in {3, 6}:
            continue
        if all(char in "0123456789abcdefABCDEF" for char in hex_value):
            return f"#{hex_value.lower()}"
    return None


def _apply_geofence_style(payload: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(geometry)
    geometry_style = normalized.get("style") if isinstance(normalized.get("style"), dict) else {}
    payload_style = payload.get("style") if isinstance(payload.get("style"), dict) else {}
    payload_geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
    payload_geometry_style = payload_geometry.get("style") if isinstance(payload_geometry.get("style"), dict) else {}
    color = _normalize_geofence_color(
        payload.get("color"),
        payload.get("fillColor"),
        payload.get("fill_color"),
        payload_style.get("color"),
        payload_style.get("fillColor"),
        payload_geometry.get("color"),
        payload_geometry_style.get("color"),
        payload_geometry_style.get("fillColor"),
        normalized.get("color"),
        geometry_style.get("color"),
        geometry_style.get("fillColor"),
    )
    if not color:
        return normalized
    style = {**geometry_style, "color": color, "fillColor": color}
    normalized["style"] = style
    normalized["color"] = color
    return normalized


def _iso_or_none(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _process_geofence_transitions(
    db: Session,
    vehicle: Vehicle,
    telemetry: VehicleTelemetry,
    payload: dict[str, Any],
) -> None:
    if telemetry.latitude is None or telemetry.longitude is None:
        return
    if not _geofence_tables_ready(db):
        return

    geofences = db.execute(
        text(
            """
            SELECT id, name, geofence_type, geometry
            FROM geofences
            WHERE company_id = :company_id
              AND active IS TRUE
              AND deleted_at IS NULL
            """
        ),
        {"company_id": vehicle.company_id},
    ).mappings().all()
    if not geofences:
        return

    gps_at = gps_datetime_from_payload(payload, telemetry.received_at)
    for geofence in geofences:
        geometry = _json_object(geofence.get("geometry"))
        inside = point_in_geofence(
            float(telemetry.latitude),
            float(telemetry.longitude),
            geofence.get("geofence_type"),
            geometry,
        )
        state = db.execute(
            text(
                """
                SELECT id, inside
                FROM vehicle_geofence_states
                WHERE vehicle_id = :vehicle_id
                  AND geofence_id = :geofence_id
                LIMIT 1
                """
            ),
            {"vehicle_id": vehicle.id, "geofence_id": geofence.get("id")},
        ).mappings().first()
        if state is None:
            db.execute(
                text(
                    """
                    INSERT INTO vehicle_geofence_states (
                        vehicle_id, geofence_id, inside, last_gps_at, last_changed_at
                    )
                    VALUES (:vehicle_id, :geofence_id, :inside, :last_gps_at, :last_changed_at)
                    """
                ),
                {
                    "vehicle_id": vehicle.id,
                    "geofence_id": geofence.get("id"),
                    "inside": inside,
                    "last_gps_at": gps_at,
                    "last_changed_at": gps_at or telemetry.received_at,
                },
            )
            continue
        if bool(state.get("inside")) == inside:
            db.execute(
                text(
                    """
                    UPDATE vehicle_geofence_states
                    SET last_gps_at = :last_gps_at,
                        updated_at = now()
                    WHERE id = :state_id
                    """
                ),
                {"state_id": state.get("id"), "last_gps_at": gps_at},
            )
            continue

        db.execute(
            text(
                """
                UPDATE vehicle_geofence_states
                SET inside = :inside,
                    last_gps_at = :last_gps_at,
                    last_changed_at = :last_changed_at,
                    updated_at = now()
                WHERE id = :state_id
                """
            ),
            {
                "state_id": state.get("id"),
                "inside": inside,
                "last_gps_at": gps_at,
                "last_changed_at": gps_at or telemetry.received_at,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO geofence_alerts (
                    vehicle_id, plate, geofence_id, geofence_name, event_type,
                    gps_at, latitude, longitude, processed, payload
                )
                VALUES (
                    :vehicle_id, :plate, :geofence_id, :geofence_name, :event_type,
                    :gps_at, :latitude, :longitude, false, CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "vehicle_id": vehicle.id,
                "plate": vehicle.plate,
                "geofence_id": geofence.get("id"),
                "geofence_name": geofence.get("name"),
                "event_type": "entry" if inside else "exit",
                "gps_at": gps_at,
                "latitude": telemetry.latitude,
                "longitude": telemetry.longitude,
                "payload": _json_dump(
                    {
                        "device_id": vehicle.unique_code or vehicle.plate or str(vehicle.id),
                        "source": payload.get("source"),
                        "event": payload.get("event"),
                        "status": payload.get("status"),
                    }
                ),
            },
        )


def _store_vehicle_telemetry(vehicle: Vehicle, payload: dict[str, Any], db: Session) -> MessageResponse:
    data = normalize_vehicle_payload(payload or {})
    lat, lon, speed, heading = _vehicle_point_values(data)
    if lat is None or lon is None:
        data["gps_validation_status"] = "invalid_coordinate"
    else:
        data["gps_validation_status"] = "ok"

    if _duplicate_vehicle_point_exists(db, vehicle_id=vehicle.id, lat=lat, lon=lon, payload=data):
        return MessageResponse(message="Punto GPS duplicado ignorado")

    telemetry = VehicleTelemetry(
        vehicle_id=vehicle.id,
        latitude=lat,
        longitude=lon,
        speed=speed,
        heading=heading,
        payload=data,
    )
    db.add(telemetry)
    db.flush()
    _process_geofence_transitions(db, vehicle, telemetry, data)
    db.commit()
    return MessageResponse(message="Telemetria de vehiculo recibida")


@router.post("/vehicle", response_model=MessageResponse)
def vehicle_telemetry(payload: VehicleTelemetryIn, db: Session = Depends(get_db)) -> MessageResponse:
    if not payload.vehicle_id:
        raise HTTPException(status_code=400, detail="vehicle_id requerido")
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicle_id, Vehicle.deleted_at.is_(None)))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehiculo no encontrado")
    return _store_vehicle_telemetry(vehicle, payload.payload or {}, db)


@router.get("/latest")
def latest_telemetry(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    _assert_map_access(db, current_user)
    drone_query = select(Drone).where(Drone.active.is_(True))
    vehicle_query = select(Vehicle).where(Vehicle.active.is_(True))
    if not _is_master(db, current_user):
        drone_query = drone_query.where(Drone.company_id == current_user.company_id)
        vehicle_query = vehicle_query.where(Vehicle.company_id == current_user.company_id)
    drones = db.scalars(drone_query).all()
    vehicles = db.scalars(vehicle_query).all()

    drone_telemetry_map: dict = {}
    if drones:
        drone_ids = [d.id for d in drones]
        rows = db.scalars(
            select(DroneTelemetry).from_statement(
                text(
                    "SELECT DISTINCT ON (drone_id) * FROM drone_telemetry"
                    " WHERE drone_id = ANY(:ids)"
                    " ORDER BY drone_id, received_at DESC"
                )
            ).params(ids=drone_ids)
        ).all()
        drone_telemetry_map = {t.drone_id: t for t in rows}

    vehicle_telemetry_map: dict = {}
    if vehicles:
        vehicle_ids = [v.id for v in vehicles]
        rows = db.scalars(
            select(VehicleTelemetry).from_statement(
                text(
                    "SELECT DISTINCT ON (vehicle_id) * FROM vehicle_telemetry"
                    " WHERE vehicle_id = ANY(:ids)"
                    " ORDER BY vehicle_id, received_at DESC"
                )
            ).params(ids=vehicle_ids)
        ).all()
        vehicle_telemetry_map = {t.vehicle_id: t for t in rows}

    items = [_latest_drone_item(d, drone_telemetry_map.get(d.id)) for d in drones]
    items += [_latest_vehicle_item(v, vehicle_telemetry_map.get(v.id)) for v in vehicles]
    return items


def _store_device_telemetry(device_id: str, payload: dict, db: Session) -> MessageResponse:
    data = payload or {}
    vehicle = db.scalar(select(Vehicle).where(Vehicle.unique_code == device_id))
    if vehicle:
        return _store_vehicle_telemetry(vehicle, data, db)

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


# ─── Historial y km ───────────────────────────────────────────────────────────

@router.get("/history")
def telemetry_history(
    vehicle_id: UUID,
    day: date = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=100000),
    include_invalid: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Historial de posiciones de un vehículo para un día (default: hoy)."""
    target_day = day or datetime.now(ECUADOR_TZ).date()
    local_start = datetime(target_day.year, target_day.month, target_day.day, tzinfo=ECUADOR_TZ)
    local_end = local_start + timedelta(days=1)
    # La consulta usa received_at para aprovechar el índice y deja una tolerancia
    # por si el punto se registró tarde respecto a la hora GPS del dispositivo.
    query_start = local_start.astimezone(timezone.utc) - timedelta(days=1)
    query_end = local_end.astimezone(timezone.utc) + timedelta(days=1)

    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None)))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    _assert_map_access(db, current_user)
    _assert_vehicle_scope(db, current_user, vehicle)

    filters = (
        VehicleTelemetry.vehicle_id == vehicle_id,
        VehicleTelemetry.received_at >= query_start,
        VehicleTelemetry.received_at < query_end,
    )

    if limit is None:
        rows = db.scalars(
            select(VehicleTelemetry)
            .where(*filters)
            .order_by(VehicleTelemetry.received_at.asc())
        ).all()
    else:
        # Si el cliente pide limite, conservar los ultimos N puntos y devolverlos en orden cronologico.
        rows = list(
            reversed(
                db.scalars(
                    select(VehicleTelemetry)
                    .where(*filters)
                    .order_by(VehicleTelemetry.received_at.desc())
                    .limit(limit)
                ).all()
            )
        )

    points, diagnostics = build_route_points(rows, include_invalid=include_invalid)
    filtered = [p for p in points if local_date_for_point(p) == target_day.isoformat()]
    if filtered:
        segment_map = _materialize_hybrid_route_segments(db, vehicle=vehicle, points=filtered, target_day=target_day)
        filtered[0]["segment_status"] = "start"
        filtered[0]["segment_reason"] = None
        filtered[0]["counted_for_km"] = False
        for point in filtered[1:]:
            _apply_segment_to_point(point, segment_map.get(str(point.get("telemetry_id") or "")))
    for point in filtered:
        point["diagnostics"] = diagnostics
    return filtered


@router.get("/km-summary")
def telemetry_km_summary(
    vehicle_id: UUID,
    from_date: date = Query(default=None),
    to_date: date = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Resumen de km recorridos por día para un rango de fechas."""
    today = datetime.now().date()
    from_d = from_date or (today - timedelta(days=29))
    to_d = to_date or today
    if (to_d - from_d).days > 366:
        raise HTTPException(status_code=400, detail="Rango máximo 366 días")

    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None)))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    _assert_map_access(db, current_user)
    _assert_vehicle_scope(db, current_user, vehicle)

    local_start = datetime(from_d.year, from_d.month, from_d.day, tzinfo=ECUADOR_TZ)
    local_end = datetime(to_d.year, to_d.month, to_d.day, tzinfo=ECUADOR_TZ) + timedelta(days=1)
    rows = db.execute(
        text(
            """
            SELECT latitude, longitude, speed, heading, payload, received_at
            FROM vehicle_telemetry
            WHERE vehicle_id = :vid
              AND received_at >= :ts_from
              AND received_at < :ts_to
            ORDER BY received_at ASC
            """
        ),
        {
            "vid": vehicle_id,
            "ts_from": local_start.astimezone(timezone.utc) - timedelta(days=1),
            "ts_to": local_end.astimezone(timezone.utc) + timedelta(days=1),
        },
    ).fetchall()

    return summarize_daily_mileage(rows, from_d, to_d)


def _fleet_report_for_group(report: dict[str, Any], group_by: str) -> Any:
    normalized_group = str(group_by or "summary").strip().lower()
    if normalized_group in {"vehicle", "vehicles", "fleet"}:
        return report.get("vehicles", [])
    if normalized_group in {"day", "daily", "date", "dates"}:
        return report.get("daily", [])
    if normalized_group in {"month", "monthly", "months"}:
        return report.get("monthly", [])
    return report


def _fleet_cache_get(cache_key: tuple[str, str, str, str]) -> dict[str, Any] | None:
    now = time.monotonic()
    with _km_fleet_cache_lock:
        cached = _km_fleet_cache.get(cache_key)
        if cached and now - cached[0] < _KM_FLEET_CACHE_TTL_SECONDS:
            return cached[1]
    return None


def _fleet_cache_set(cache_key: tuple[str, str, str, str], report: dict[str, Any]) -> None:
    now = time.monotonic()
    with _km_fleet_cache_lock:
        _km_fleet_cache[cache_key] = (now, report)
        if len(_km_fleet_cache) <= _KM_FLEET_CACHE_MAX_ITEMS:
            return
        stale_keys = [
            key
            for key, value in _km_fleet_cache.items()
            if now - value[0] > (_KM_FLEET_CACHE_TTL_SECONDS * 4)
        ]
        for key in stale_keys:
            _km_fleet_cache.pop(key, None)
        while len(_km_fleet_cache) > _KM_FLEET_CACHE_MAX_ITEMS:
            oldest_key = min(_km_fleet_cache, key=lambda key: _km_fleet_cache[key][0])
            _km_fleet_cache.pop(oldest_key, None)


@router.get("/km-fleet")
def telemetry_km_fleet(
    from_date: date = Query(default=None),
    to_date: date = Query(default=None),
    group_by: str = "summary",
    company_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resumen agregado de kilometraje de flota sin cargar puntos GPS crudos al dashboard."""
    today = datetime.now(ECUADOR_TZ).date()
    from_d = from_date or (today - timedelta(days=29))
    to_d = to_date or today
    if from_d > to_d:
        raise HTTPException(status_code=400, detail="Rango de fechas invalido")
    range_days = (to_d - from_d).days + 1
    if range_days > 366:
        raise HTTPException(status_code=400, detail="Rango máximo 366 días")

    _assert_map_access(db, current_user)
    is_master = _is_master(db, current_user)
    scope_company_id = company_id if is_master and company_id else (None if is_master else current_user.company_id)
    if not is_master and not scope_company_id:
        empty_report = {
            "from_date": from_d.isoformat(),
            "to_date": to_d.isoformat(),
            "range_days": range_days,
            "totals": {"total_km": 0.0, "active_vehicles": 0, "total_vehicles": 0, "total_points": 0},
            "vehicles": [],
            "daily": [],
            "monthly": [],
        }
        return _fleet_report_for_group(empty_report, group_by)

    company_filter = "AND v.company_id = :scope_company_id" if scope_company_id else ""
    local_start = datetime(from_d.year, from_d.month, from_d.day, tzinfo=ECUADOR_TZ)
    local_end = datetime(to_d.year, to_d.month, to_d.day, tzinfo=ECUADOR_TZ) + timedelta(days=1)
    cache_key = (
        str(getattr(current_user, "id", "")),
        str(scope_company_id or "all"),
        from_d.isoformat(),
        to_d.isoformat(),
    )
    cached_report = _fleet_cache_get(cache_key)
    if cached_report:
        return _fleet_report_for_group(cached_report, group_by)

    if _db_is_postgres(db):
        db.execute(text("SET LOCAL statement_timeout = '45s'"))

    rows = db.execute(
        text(
            f"""
            WITH scoped_vehicles AS (
                SELECT
                    base.id,
                    base.company_id,
                    base.name,
                    base.plate,
                    base.unique_code,
                    base.vehicle_type,
                    base.vehicle_subtype,
                    base.driver_name,
                    COALESCE(
                        NULLIF(UPPER(REGEXP_REPLACE(base.plate_match, '^([A-Z]{{2,4}})[ -]?([0-9]{{3,5}})$', '\\1-\\2')), ''),
                        NULLIF(base.plate, ''),
                        NULLIF(base.name, ''),
                        NULLIF(base.unique_code, ''),
                        base.id::text
                    ) AS fleet_label,
                    COALESCE(
                        NULLIF(REGEXP_REPLACE(UPPER(base.plate_match), '[^A-Z0-9]', '', 'g'), ''),
                        NULLIF(REGEXP_REPLACE(UPPER(COALESCE(base.plate, base.name, base.unique_code, base.id::text)), '[^A-Z0-9]', '', 'g'), ''),
                        base.id::text
                    ) AS fleet_key
                FROM (
                    SELECT
                        v.id,
                        v.company_id,
                        v.name,
                        v.plate,
                        v.unique_code,
                        v.vehicle_type,
                        v.vehicle_subtype,
                        v.driver_name,
                        SUBSTRING(UPPER(COALESCE(v.plate, v.name, v.unique_code, '')) FROM '([A-Z]{{2,4}}[ -]?[0-9]{{3,5}})') AS plate_match
                    FROM vehicles v
                    WHERE v.active IS TRUE
                      AND v.deleted_at IS NULL
                      {company_filter}
                ) base
            ),
            raw_points AS (
                SELECT
                    vt.id,
                    vt.vehicle_id,
                    sv.fleet_key,
                    sv.fleet_label,
                    sv.driver_name,
                    sv.vehicle_type,
                    sv.vehicle_subtype,
                    vt.latitude,
                    vt.longitude,
                    vt.speed,
                    vt.received_at,
                    CASE
                        WHEN (vt.payload->>'gps_datetime_iso') ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T'
                        THEN (vt.payload->>'gps_datetime_iso')::timestamptz
                        ELSE vt.received_at
                    END AS gps_at
                FROM vehicle_telemetry vt
                JOIN scoped_vehicles sv ON sv.id = vt.vehicle_id
                WHERE vt.received_at >= :query_start
                  AND vt.received_at < :query_end
                  AND vt.latitude IS NOT NULL
                  AND vt.longitude IS NOT NULL
                  AND vt.latitude BETWEEN -90 AND 90
                  AND vt.longitude BETWEEN -180 AND 180
                  AND NOT (ABS(vt.latitude) < 0.000001 AND ABS(vt.longitude) < 0.000001)
            ),
            points AS (
                SELECT
                    rp.*,
                    (rp.gps_at AT TIME ZONE 'America/Guayaquil')::date AS local_day
                FROM raw_points rp
                WHERE rp.gps_at >= :period_start
                  AND rp.gps_at < :period_end
            ),
            ordered AS (
                SELECT
                    p.*,
                    LAG(p.latitude) OVER w AS prev_latitude,
                    LAG(p.longitude) OVER w AS prev_longitude,
                    LAG(p.gps_at) OVER w AS prev_gps_at,
                    LAG(p.local_day) OVER w AS prev_local_day
                FROM points p
                WINDOW w AS (PARTITION BY p.fleet_key ORDER BY p.gps_at ASC, p.received_at ASC, p.id ASC)
            ),
            distance_calc AS (
                SELECT
                    o.*,
                    EXTRACT(EPOCH FROM (o.gps_at - o.prev_gps_at)) AS elapsed_seconds,
                    CASE
                        WHEN o.prev_latitude IS NULL THEN NULL
                        ELSE LEAST(
                            1.0,
                            GREATEST(
                                0.0,
                                POWER(SIN(RADIANS(o.latitude - o.prev_latitude) / 2), 2)
                                + COS(RADIANS(o.prev_latitude))
                                  * COS(RADIANS(o.latitude))
                                  * POWER(SIN(RADIANS(o.longitude - o.prev_longitude) / 2), 2)
                            )
                        )
                    END AS haversine_a
                FROM ordered o
            ),
            segments AS (
                SELECT
                    dc.*,
                    CASE
                        WHEN dc.haversine_a IS NULL THEN 0.0
                        ELSE 6371.0 * 2.0 * ATAN2(SQRT(dc.haversine_a), SQRT(GREATEST(0.0, 1.0 - dc.haversine_a)))
                    END AS distance_km
                FROM distance_calc dc
            ),
            daily AS (
                SELECT
                    s.fleet_key,
                    MIN(s.fleet_label) AS label,
                    MIN(NULLIF(s.driver_name, '')) AS driver_name,
                    MIN(NULLIF(s.vehicle_type, '')) AS vehicle_type,
                    MIN(NULLIF(s.vehicle_subtype, '')) AS vehicle_subtype,
                    s.local_day AS period,
                    COUNT(*)::bigint AS points,
                    MAX(COALESCE(s.speed, 0)) AS max_speed,
                    SUM(
                        CASE
                            WHEN s.prev_latitude IS NOT NULL
                              AND s.local_day = s.prev_local_day
                              AND s.elapsed_seconds > 0
                              AND s.elapsed_seconds <= :max_segment_gap_seconds
                              AND s.distance_km <= :max_segment_distance_km
                              AND (s.distance_km / (s.elapsed_seconds / 3600.0)) <= :max_reasonable_speed_kmh
                            THEN s.distance_km
                            ELSE 0
                        END
                    ) AS km
                FROM segments s
                WHERE s.local_day >= CAST(:from_d AS date)
                  AND s.local_day <= CAST(:to_d AS date)
                GROUP BY s.fleet_key, s.local_day
            ),
            vehicle_rows AS (
                SELECT
                    'vehicle'::text AS row_type,
                    sg.vehicle_id,
                    sg.label,
                    sg.driver_name,
                    sg.vehicle_type,
                    sg.vehicle_subtype,
                    sg.source_count,
                    NULL::date AS period,
                    COALESCE(SUM(d.km), 0)::double precision AS total_km,
                    COALESCE(MAX(d.max_speed), 0)::double precision AS max_speed,
                    NULL::bigint AS active_vehicles,
                    COUNT(d.period) FILTER (WHERE d.km > 0.05)::bigint AS active_days,
                    COALESCE(SUM(d.points), 0)::bigint AS total_points
                FROM (
                    SELECT
                        sv.fleet_key,
                        STRING_AGG(DISTINCT sv.id::text, ',') AS vehicle_id,
                        MIN(sv.fleet_label)::text AS label,
                        MIN(NULLIF(sv.driver_name, ''))::text AS driver_name,
                        MIN(NULLIF(sv.vehicle_type, ''))::text AS vehicle_type,
                        MIN(NULLIF(sv.vehicle_subtype, ''))::text AS vehicle_subtype,
                        COUNT(DISTINCT sv.id)::bigint AS source_count
                    FROM scoped_vehicles sv
                    GROUP BY sv.fleet_key
                ) sg
                LEFT JOIN daily d ON d.fleet_key = sg.fleet_key
                GROUP BY sg.fleet_key, sg.vehicle_id, sg.label, sg.driver_name, sg.vehicle_type, sg.vehicle_subtype, sg.source_count
            ),
            daily_periods AS (
                SELECT generate_series(CAST(:from_d AS date), CAST(:to_d AS date), INTERVAL '1 day')::date AS period
            ),
            daily_rows AS (
                SELECT
                    'daily'::text AS row_type,
                    NULL::text AS vehicle_id,
                    NULL::text AS label,
                    NULL::text AS driver_name,
                    NULL::text AS vehicle_type,
                    NULL::text AS vehicle_subtype,
                    NULL::bigint AS source_count,
                    p.period AS period,
                    COALESCE(SUM(d.km), 0)::double precision AS total_km,
                    COALESCE(MAX(d.max_speed), 0)::double precision AS max_speed,
                    COUNT(DISTINCT d.fleet_key) FILTER (WHERE d.km > 0.05)::bigint AS active_vehicles,
                    CASE WHEN COALESCE(SUM(d.km), 0) > 0.05 THEN 1 ELSE 0 END::bigint AS active_days,
                    COALESCE(SUM(d.points), 0)::bigint AS total_points
                FROM daily_periods p
                LEFT JOIN daily d ON d.period = p.period
                GROUP BY p.period
            ),
            monthly_periods AS (
                SELECT generate_series(
                    date_trunc('month', CAST(:from_d AS date)::timestamp)::date,
                    date_trunc('month', CAST(:to_d AS date)::timestamp)::date,
                    INTERVAL '1 month'
                )::date AS period
            ),
            monthly_rows AS (
                SELECT
                    'monthly'::text AS row_type,
                    NULL::text AS vehicle_id,
                    NULL::text AS label,
                    NULL::text AS driver_name,
                    NULL::text AS vehicle_type,
                    NULL::text AS vehicle_subtype,
                    NULL::bigint AS source_count,
                    p.period AS period,
                    COALESCE(SUM(d.km), 0)::double precision AS total_km,
                    COALESCE(MAX(d.max_speed), 0)::double precision AS max_speed,
                    COUNT(DISTINCT d.fleet_key) FILTER (WHERE d.km > 0.05)::bigint AS active_vehicles,
                    COUNT(DISTINCT d.period) FILTER (WHERE d.km > 0.05)::bigint AS active_days,
                    COALESCE(SUM(d.points), 0)::bigint AS total_points
                FROM monthly_periods p
                LEFT JOIN daily d ON date_trunc('month', d.period::timestamp)::date = p.period
                GROUP BY p.period
            )
            SELECT * FROM vehicle_rows
            UNION ALL
            SELECT * FROM daily_rows
            UNION ALL
            SELECT * FROM monthly_rows
            ORDER BY row_type ASC, period ASC NULLS FIRST, total_km DESC
            """
        ),
        {
            "scope_company_id": scope_company_id,
            "query_start": local_start.astimezone(timezone.utc) - timedelta(days=1),
            "query_end": local_end.astimezone(timezone.utc) + timedelta(days=1),
            "period_start": local_start.astimezone(timezone.utc),
            "period_end": local_end.astimezone(timezone.utc),
            "from_d": from_d,
            "to_d": to_d,
            "max_segment_gap_seconds": MAX_SEGMENT_GAP_SECONDS,
            "max_segment_distance_km": MAX_SEGMENT_DISTANCE_KM,
            "max_reasonable_speed_kmh": MAX_REASONABLE_SPEED_KMH,
        },
    ).mappings().all()

    def _period_value(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)

    vehicles: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "total_km": round(float(row.get("total_km") or 0.0), 2),
            "max_speed": round(float(row.get("max_speed") or 0.0), 1),
            "active_vehicles": int(row.get("active_vehicles") or 0),
            "active_days": int(row.get("active_days") or 0),
            "total_points": int(row.get("total_points") or 0),
        }
        row_type = row.get("row_type")
        if row_type == "vehicle":
            item.update({
                "vehicle_id": row.get("vehicle_id"),
                "label": row.get("label") or row.get("vehicle_id"),
                "driver_name": row.get("driver_name") or "",
                "chofer": row.get("driver_name") or "",
                "vehicle_type": row.get("vehicle_type") or "",
                "vehicle_subtype": row.get("vehicle_subtype") or "",
                "source_count": int(row.get("source_count") or 1),
            })
            vehicles.append(item)
        elif row_type == "daily":
            item["period"] = _period_value(row.get("period"))
            item["date"] = item["period"]
            daily.append(item)
        elif row_type == "monthly":
            item["period"] = _period_value(row.get("period"))
            item["month"] = item["period"]
            monthly.append(item)

    vehicles.sort(key=lambda value: value["total_km"], reverse=True)
    totals = {
        "total_km": round(sum(item["total_km"] for item in vehicles), 2),
        "active_vehicles": sum(1 for item in vehicles if item["total_km"] > 0.05),
        "total_vehicles": len(vehicles),
        "total_points": sum(item["total_points"] for item in vehicles),
        "active_days": sum(1 for item in daily if item["total_km"] > 0.05),
        "max_speed": round(max((item["max_speed"] for item in vehicles), default=0.0), 1),
    }
    report = {
        "from_date": from_d.isoformat(),
        "to_date": to_d.isoformat(),
        "range_days": range_days,
        "totals": totals,
        "vehicles": vehicles,
        "daily": daily,
        "monthly": monthly,
    }
    _fleet_cache_set(cache_key, report)
    return _fleet_report_for_group(report, group_by)


# ─── Geocercas y alertas ─────────────────────────────────────────────────────

def _geofence_to_dict(geofence: Any) -> dict[str, Any]:
    geometry = _json_object(_row_value(geofence, "geometry"))
    style = geometry.get("style") if isinstance(geometry.get("style"), dict) else {}
    color = _normalize_geofence_color(geometry.get("color"), style.get("color"), style.get("fillColor"))
    return {
        "id": str(_row_value(geofence, "id")),
        "company_id": str(_row_value(geofence, "company_id")),
        "name": _row_value(geofence, "name"),
        "type": _row_value(geofence, "geofence_type"),
        "geofence_type": _row_value(geofence, "geofence_type"),
        "geometry": geometry,
        "coordinates": geometry.get("coordinates"),
        "style": style,
        "color": color,
        "active": bool(_row_value(geofence, "active")),
        "description": _row_value(geofence, "description"),
        "created_at": _iso_or_none(_row_value(geofence, "created_at")),
        "updated_at": _iso_or_none(_row_value(geofence, "updated_at")),
    }


def _alert_to_dict(alert: Any) -> dict[str, Any]:
    return {
        "id": str(_row_value(alert, "id")),
        "vehicle_id": str(_row_value(alert, "vehicle_id")),
        "plate": _row_value(alert, "plate"),
        "geofence_id": str(_row_value(alert, "geofence_id")),
        "geofence_name": _row_value(alert, "geofence_name"),
        "event_type": _row_value(alert, "event_type"),
        "gps_at": _iso_or_none(_row_value(alert, "gps_at")),
        "recorded_at": _iso_or_none(_row_value(alert, "recorded_at")),
        "lat": _row_value(alert, "latitude"),
        "lon": _row_value(alert, "longitude"),
        "processed": bool(_row_value(alert, "processed")),
        "payload": _json_object(_row_value(alert, "payload")),
    }


def _fetch_geofence(db: Session, geofence_id: UUID) -> Any | None:
    return db.execute(
        text(
            """
            SELECT id, company_id, name, geofence_type, geometry, active,
                   description, created_at, updated_at
            FROM geofences
            WHERE id = :geofence_id
              AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"geofence_id": geofence_id},
    ).mappings().first()


def _resolve_geofence_company_id(payload: dict[str, Any], db: Session, current_user) -> UUID:
    if not _is_master(db, current_user):
        if not current_user.company_id:
            raise HTTPException(status_code=400, detail="company_id requerido")
        return current_user.company_id

    raw_company_id = _first_present(
        payload.get("company_id"),
        payload.get("organization_id"),
        payload.get("organizacion_id"),
    )
    if raw_company_id:
        try:
            company_id = UUID(str(raw_company_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="company_id invalido") from exc
        exists = db.scalar(
            select(Company.id).where(
                Company.id == company_id,
                Company.active.is_(True),
                Company.deleted_at.is_(None),
            )
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Organizacion no encontrada")
        return company_id

    if current_user.company_id:
        return current_user.company_id

    company_ids = db.scalars(
        select(Company.id)
        .where(Company.active.is_(True), Company.deleted_at.is_(None))
        .order_by(Company.name.asc())
        .limit(2)
    ).all()
    if len(company_ids) == 1:
        return company_ids[0]
    raise HTTPException(status_code=400, detail="company_id requerido")


def _normalize_geofence_geometry(payload: dict[str, Any], geofence_type: str) -> dict[str, Any]:
    geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
    if geofence_type == "circle":
        center = geometry.get("center") if isinstance(geometry.get("center"), dict) else {}
        lat = coerce_float(_first_present(payload.get("lat"), payload.get("latitude"), center.get("lat"), geometry.get("lat")))
        lon = coerce_float(_first_present(payload.get("lon"), payload.get("lng"), payload.get("longitude"), center.get("lon"), center.get("lng"), geometry.get("lon"), geometry.get("lng")))
        radius_m = coerce_float(_first_present(payload.get("radius_m"), payload.get("radius"), geometry.get("radius_m"), geometry.get("radius")))
        if lat is None or lon is None or radius_m is None or radius_m <= 0:
            raise HTTPException(status_code=400, detail="Geocerca circular invalida")
        normalized = {"type": "Circle", "center": {"lat": lat, "lon": lon}, "radius_m": radius_m}
        return _apply_geofence_style(payload, normalized)

    coordinates = geometry.get("coordinates") or payload.get("coordinates") or []
    if not isinstance(coordinates, list) or len(coordinates) < 3:
        raise HTTPException(status_code=400, detail="Geocerca poligonal invalida")
    coordinate_order = str(
        payload.get("coordinate_order") or geometry.get("coordinate_order") or ""
    ).strip().lower()
    if str(geometry.get("type") or "").lower() == "polygon":
        normalized = {"type": "Polygon", "coordinates": coordinates}
        if coordinate_order:
            normalized["coordinate_order"] = coordinate_order
        return _apply_geofence_style(payload, normalized)
    normalized = {"type": "Polygon", "coordinate_order": coordinate_order or "latlon", "coordinates": coordinates}
    return _apply_geofence_style(payload, normalized)


@router.get("/geofences")
def geofences(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    _assert_map_access(db, current_user)
    _assert_geofence_tables_ready(db)
    params: dict[str, Any] = {}
    company_filter = ""
    if not _is_master(db, current_user):
        company_filter = "AND company_id = :company_id"
        params["company_id"] = current_user.company_id
    rows = db.execute(
        text(
            f"""
            SELECT id, company_id, name, geofence_type, geometry, active,
                   description, created_at, updated_at
            FROM geofences
            WHERE deleted_at IS NULL
            {company_filter}
            ORDER BY name ASC
            """
        ),
        params,
    ).mappings().all()
    return [_geofence_to_dict(item) for item in rows]


@router.post("/geofences")
def geofence_create(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    _assert_fleet_manage_access(db, current_user)
    _assert_geofence_tables_ready(db)
    name = str(payload.get("name") or payload.get("nombre") or "").strip()
    geofence_type = str(payload.get("type") or payload.get("geofence_type") or "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    if geofence_type not in {"circle", "polygon"}:
        raise HTTPException(status_code=400, detail="Tipo de geocerca invalido")
    company_id = _resolve_geofence_company_id(payload, db, current_user)
    geometry = _normalize_geofence_geometry(payload, geofence_type)
    row = db.execute(
        text(
            """
            INSERT INTO geofences (
                company_id, name, geofence_type, geometry, active, description
            )
            VALUES (
                :company_id, :name, :geofence_type, CAST(:geometry AS jsonb), :active, :description
            )
            RETURNING id, company_id, name, geofence_type, geometry, active,
                      description, created_at, updated_at
            """
        ),
        {
            "company_id": company_id,
            "name": name,
            "geofence_type": geofence_type,
            "geometry": _json_dump(geometry),
            "active": _bool_from_payload(payload.get("active"), True),
            "description": payload.get("description") or payload.get("descripcion"),
        },
    ).mappings().first()
    db.commit()
    return _geofence_to_dict(row)


@router.put("/geofences/{geofence_id}")
def geofence_update(
    geofence_id: UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    _assert_fleet_manage_access(db, current_user)
    _assert_geofence_tables_ready(db)
    geofence = _fetch_geofence(db, geofence_id)
    if not geofence:
        raise HTTPException(status_code=404, detail="Geocerca no encontrada")
    if not _is_master(db, current_user) and str(geofence.get("company_id")) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Geocerca fuera de la organizacion")
    name = str(payload.get("name") or payload.get("nombre") or geofence.get("name")).strip()
    geofence_type = str(payload.get("type") or payload.get("geofence_type") or geofence.get("geofence_type")).strip().lower()
    if geofence_type not in {"circle", "polygon"}:
        raise HTTPException(status_code=400, detail="Tipo de geocerca invalido")
    geometry = _json_object(geofence.get("geometry"))
    geometry_payload_changed = any(
        key in payload
        for key in ("geometry", "coordinates", "lat", "latitude", "lon", "lng", "longitude", "radius_m", "radius")
    )
    if geometry_payload_changed:
        geometry = _normalize_geofence_geometry(payload, geofence_type)
    else:
        geometry = _apply_geofence_style(payload, geometry)
    description = payload.get("description", payload.get("descripcion", geofence.get("description")))
    row = db.execute(
        text(
            """
            UPDATE geofences
            SET name = :name,
                geofence_type = :geofence_type,
                geometry = CAST(:geometry AS jsonb),
                active = :active,
                description = :description,
                updated_at = now()
            WHERE id = :geofence_id
              AND deleted_at IS NULL
            RETURNING id, company_id, name, geofence_type, geometry, active,
                      description, created_at, updated_at
            """
        ),
        {
            "geofence_id": geofence_id,
            "name": name,
            "geofence_type": geofence_type,
            "geometry": _json_dump(geometry),
            "active": _bool_from_payload(payload.get("active"), bool(geofence.get("active"))),
            "description": description,
        },
    ).mappings().first()
    db.commit()
    return _geofence_to_dict(row)


@router.delete("/geofences/{geofence_id}", response_model=MessageResponse)
def geofence_delete(
    geofence_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MessageResponse:
    _assert_fleet_manage_access(db, current_user)
    _assert_geofence_tables_ready(db)
    geofence = _fetch_geofence(db, geofence_id)
    if not geofence:
        raise HTTPException(status_code=404, detail="Geocerca no encontrada")
    if not _is_master(db, current_user) and str(geofence.get("company_id")) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Geocerca fuera de la organizacion")
    db.execute(
        text(
            """
            UPDATE geofences
            SET deleted_at = now(),
                active = false,
                updated_at = now()
            WHERE id = :geofence_id
            """
        ),
        {"geofence_id": geofence_id},
    )
    db.commit()
    return MessageResponse(message="Geocerca eliminada")


@router.get("/geofence-alerts")
def geofence_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    processed: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    _assert_map_access(db, current_user)
    _assert_geofence_tables_ready(db)
    filters: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if processed is not None:
        filters.append("a.processed = :processed")
        params["processed"] = processed
    if not _is_master(db, current_user):
        filters.append("g.company_id = :company_id")
        params["company_id"] = current_user.company_id
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = db.execute(
        text(
            f"""
            SELECT a.id, a.vehicle_id, a.plate, a.geofence_id, a.geofence_name,
                   a.event_type, a.gps_at, a.recorded_at, a.latitude,
                   a.longitude, a.processed, a.payload
            FROM geofence_alerts a
            JOIN geofences g ON g.id = a.geofence_id
            {where_clause}
            ORDER BY a.recorded_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_alert_to_dict(row) for row in rows]


@router.patch("/geofence-alerts/{alert_id}/processed")
def geofence_alert_processed(
    alert_id: UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    _assert_fleet_manage_access(db, current_user)
    _assert_geofence_tables_ready(db)
    alert = db.execute(
        text(
            """
            SELECT a.id, a.vehicle_id, a.plate, a.geofence_id, a.geofence_name,
                   a.event_type, a.gps_at, a.recorded_at, a.latitude,
                   a.longitude, a.processed, a.payload, g.company_id
            FROM geofence_alerts a
            JOIN geofences g ON g.id = a.geofence_id
            WHERE a.id = :alert_id
            LIMIT 1
            """
        ),
        {"alert_id": alert_id},
    ).mappings().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    if not _is_master(db, current_user) and str(alert.get("company_id")) != str(current_user.company_id):
        raise HTTPException(status_code=403, detail="Alerta fuera de la organizacion")
    row = db.execute(
        text(
            """
            UPDATE geofence_alerts
            SET processed = :processed
            WHERE id = :alert_id
            RETURNING id, vehicle_id, plate, geofence_id, geofence_name, event_type,
                      gps_at, recorded_at, latitude, longitude, processed, payload
            """
        ),
        {"alert_id": alert_id, "processed": _bool_from_payload(payload.get("processed"), True)},
    ).mappings().first()
    db.commit()
    return _alert_to_dict(row)


@router.post("/{device_id}/gps", response_model=MessageResponse)
def device_gps_telemetry(device_id: str, payload: dict, db: Session = Depends(get_db)) -> MessageResponse:
    return _store_device_telemetry(device_id, payload, db)


@router.post("/{device_id}", response_model=MessageResponse)
def device_telemetry(device_id: str, payload: dict, db: Session = Depends(get_db)) -> MessageResponse:
    return _store_device_telemetry(device_id, payload, db)
