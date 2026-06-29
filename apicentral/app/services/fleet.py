from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen


ECUADOR_TZ = timezone(timedelta(hours=-5))
MAX_REASONABLE_SPEED_KMH = 180.0
MAX_SEGMENT_GAP_SECONDS = 30 * 60
MAX_SEGMENT_DISTANCE_KM = 8.0


def coerce_float(value: Any) -> float | None:
    try:
        if value in ("", "---", None):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_gps_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        epoch = float(value)
        if epoch > 99_999_999_999:
            epoch /= 1000
        try:
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    raw = str(value).strip()
    if not raw:
        return None
    if raw.replace(".", "", 1).isdigit():
        return parse_gps_datetime(float(raw))

    iso_raw = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%y %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=ECUADOR_TZ)
        except ValueError:
            continue
    return None


def gps_datetime_from_payload(payload: dict[str, Any], fallback: datetime | None = None) -> datetime | None:
    source = payload if isinstance(payload, dict) else {}
    for key in (
        "gps_datetime_iso",
        "gps_recorded_at",
        "gps_datetime",
        "gps_api_timestamp",
        "timestamp",
        "source_ts",
    ):
        parsed = parse_gps_datetime(source.get(key))
        if parsed:
            return parsed
    return fallback if fallback and fallback.tzinfo else (fallback.replace(tzinfo=timezone.utc) if fallback else None)


def normalize_vehicle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    gps_dt = gps_datetime_from_payload(data)
    if gps_dt:
        data["gps_datetime_iso"] = gps_dt.astimezone(timezone.utc).isoformat()
        data["gps_epoch_ms"] = int(gps_dt.timestamp() * 1000)
    return data


def is_valid_coordinate(lat: Any, lon: Any) -> bool:
    lat_f = coerce_float(lat)
    lon_f = coerce_float(lon)
    if lat_f is None or lon_f is None:
        return False
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return False
    return not (abs(lat_f) < 0.000001 and abs(lon_f) < 0.000001)


def coordinate_reasons(lat: Any, lon: Any) -> list[str]:
    lat_f = coerce_float(lat)
    lon_f = coerce_float(lon)
    reasons: list[str] = []
    if lat_f is None:
        reasons.append("latitude_missing")
    if lon_f is None:
        reasons.append("longitude_missing")
    if lat_f is not None and not (-90 <= lat_f <= 90):
        reasons.append("latitude_out_of_range")
    if lon_f is not None and not (-180 <= lon_f <= 180):
        reasons.append("longitude_out_of_range")
    if lat_f is not None and lon_f is not None and abs(lat_f) < 0.000001 and abs(lon_f) < 0.000001:
        reasons.append("zero_zero_coordinate")
    return reasons


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, key):
        return getattr(row, key)
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def _point_from_row(row: Any) -> dict[str, Any]:
    payload = _row_value(row, "payload", {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    received_at = _row_value(row, "received_at")
    gps_at = gps_datetime_from_payload(payload, received_at)
    lat = coerce_float(_row_value(row, "latitude"))
    lon = coerce_float(_row_value(row, "longitude"))
    speed = coerce_float(_row_value(row, "speed"))
    heading = coerce_float(_row_value(row, "heading"))
    reasons = coordinate_reasons(lat, lon)
    return {
        "telemetry_id": str(_row_value(row, "id") or ""),
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "heading": heading,
        "received_at": received_at.isoformat() if isinstance(received_at, datetime) else None,
        "gps_at": gps_at,
        "gps_time": gps_at.astimezone(timezone.utc).isoformat() if gps_at else None,
        "timestamp": gps_at.astimezone(timezone.utc).isoformat() if gps_at else (received_at.isoformat() if isinstance(received_at, datetime) else None),
        "event": payload.get("event"),
        "ignition": payload.get("ignition"),
        "address": payload.get("address"),
        "valid": len(reasons) == 0,
        "reasons": reasons,
        "segment_status": "start",
        "segment_reason": None,
        "distance_km": 0.0,
        "elapsed_seconds": 0.0,
        "implied_speed_kmh": 0.0,
        "counted_for_km": False,
    }


def _segment_raw_geometry(previous: dict[str, Any], point: dict[str, Any]) -> list[list[float]]:
    return [[float(previous["lat"]), float(previous["lon"])], [float(point["lat"]), float(point["lon"])]]


def _osrm_coordinates_to_latlon(coordinates: Any) -> list[list[float]]:
    result: list[list[float]] = []
    if not isinstance(coordinates, list):
        return result
    for coord in coordinates:
        if not isinstance(coord, list) or len(coord) < 2:
            continue
        lon = coerce_float(coord[0])
        lat = coerce_float(coord[1])
        if lat is not None and lon is not None:
            result.append([lat, lon])
    return result


def match_segment_with_osrm(
    previous: dict[str, Any],
    point: dict[str, Any],
    *,
    osrm_base_url: str,
    confidence_min: float,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    """Map Matching de un tramo. Devuelve None si OSRM no tiene confianza suficiente."""
    base_url = str(osrm_base_url or "").strip().rstrip("/")
    if not base_url:
        return None
    coords = f"{previous['lon']},{previous['lat']};{point['lon']},{point['lat']}"
    path = quote(coords, safe=",;")
    url = (
        f"{base_url}/match/v1/driving/{path}"
        "?geometries=geojson&overview=full&steps=false&radiuses=60;60&gaps=ignore"
    )
    try:
        request = Request(url, headers={"User-Agent": "RobiotecFleet/1.0"})
        with urlopen(request, timeout=max(0.5, float(timeout_seconds or 3.0))) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if payload.get("code") != "Ok":
        return None
    matchings = payload.get("matchings")
    if not isinstance(matchings, list) or not matchings:
        return None
    matching = matchings[0] if isinstance(matchings[0], dict) else {}
    confidence = coerce_float(matching.get("confidence")) or 0.0
    if confidence < float(confidence_min or 0.0):
        return None
    geometry = matching.get("geometry") if isinstance(matching.get("geometry"), dict) else {}
    latlon = _osrm_coordinates_to_latlon(geometry.get("coordinates"))
    if len(latlon) < 2:
        return None
    distance_km = (coerce_float(matching.get("distance")) or 0.0) / 1000.0
    return {
        "segment_kind": "osrm",
        "segment_reason": None,
        "confidence": confidence,
        "distance_km": distance_km,
        "geometry": latlon,
    }


def build_hybrid_segment(
    previous: dict[str, Any],
    point: dict[str, Any],
    *,
    inside_geofence: bool,
    osrm_base_url: str,
    confidence_min: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    raw_geometry = _segment_raw_geometry(previous, point)
    status = str(point.get("segment_status") or "normal").lower()
    raw_distance = float(point.get("distance_km") or 0.0)
    if status in {"gap", "suspicious"}:
        return {
            "segment_kind": "suspicious",
            "segment_status": "suspicious",
            "segment_reason": point.get("segment_reason") or status,
            "distance_km": raw_distance,
            "elapsed_seconds": float(point.get("elapsed_seconds") or 0.0),
            "implied_speed_kmh": float(point.get("implied_speed_kmh") or 0.0),
            "confidence": None,
            "geometry": raw_geometry,
            "counted_for_km": False,
        }
    if inside_geofence:
        return {
            "segment_kind": "raw",
            "segment_status": "raw",
            "segment_reason": "inside_geofence",
            "distance_km": raw_distance,
            "elapsed_seconds": float(point.get("elapsed_seconds") or 0.0),
            "implied_speed_kmh": float(point.get("implied_speed_kmh") or 0.0),
            "confidence": None,
            "geometry": raw_geometry,
            "counted_for_km": True,
        }

    matched = match_segment_with_osrm(
        previous,
        point,
        osrm_base_url=osrm_base_url,
        confidence_min=confidence_min,
        timeout_seconds=timeout_seconds,
    )
    if matched:
        matched.update({
            "segment_status": "osrm",
            "elapsed_seconds": float(point.get("elapsed_seconds") or 0.0),
            "implied_speed_kmh": float(point.get("implied_speed_kmh") or 0.0),
            "counted_for_km": True,
        })
        return matched

    return {
        "segment_kind": "raw",
        "segment_status": "raw",
        "segment_reason": "osrm_no_match",
        "distance_km": raw_distance,
        "elapsed_seconds": float(point.get("elapsed_seconds") or 0.0),
        "implied_speed_kmh": float(point.get("implied_speed_kmh") or 0.0),
        "confidence": None,
        "geometry": raw_geometry,
        "counted_for_km": True,
    }


def build_route_points(rows: Iterable[Any], *, include_invalid: bool = False) -> tuple[list[dict[str, Any]], dict[str, int]]:
    points = [_point_from_row(row) for row in rows]
    points.sort(key=lambda p: (p.get("gps_at") or datetime.min.replace(tzinfo=timezone.utc), p.get("received_at") or ""))

    diagnostics = {
        "raw_points": len(points),
        "valid_points": 0,
        "invalid_points": 0,
        "duplicate_points": 0,
        "gap_segments": 0,
        "suspicious_segments": 0,
        "normal_segments": 0,
    }
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str | None]] = set()
    previous: dict[str, Any] | None = None

    for point in points:
        if not point["valid"]:
            diagnostics["invalid_points"] += 1
            if include_invalid:
                result.append(_public_point(point))
            continue

        dedupe_key = (
            round(float(point["lat"]), 6),
            round(float(point["lon"]), 6),
            point.get("gps_time"),
        )
        if dedupe_key in seen:
            diagnostics["duplicate_points"] += 1
            continue
        seen.add(dedupe_key)
        diagnostics["valid_points"] += 1

        if previous:
            distance_km = haversine_km(previous["lat"], previous["lon"], point["lat"], point["lon"])
            elapsed_seconds = 0.0
            if previous.get("gps_at") and point.get("gps_at"):
                elapsed_seconds = (point["gps_at"] - previous["gps_at"]).total_seconds()
            implied_speed = (distance_km / (elapsed_seconds / 3600)) if elapsed_seconds > 0 else 0.0

            point["distance_km"] = distance_km
            point["elapsed_seconds"] = elapsed_seconds
            point["implied_speed_kmh"] = implied_speed
            point["segment_status"] = "normal"
            point["counted_for_km"] = True

            if elapsed_seconds <= 0:
                point["segment_status"] = "suspicious"
                point["segment_reason"] = "non_increasing_gps_time"
                point["counted_for_km"] = False
                diagnostics["suspicious_segments"] += 1
            elif elapsed_seconds > MAX_SEGMENT_GAP_SECONDS:
                point["segment_status"] = "gap"
                point["segment_reason"] = "large_time_gap"
                point["counted_for_km"] = False
                diagnostics["gap_segments"] += 1
            elif distance_km > MAX_SEGMENT_DISTANCE_KM:
                point["segment_status"] = "gap"
                point["segment_reason"] = "large_distance_gap"
                point["counted_for_km"] = False
                diagnostics["gap_segments"] += 1
            elif implied_speed > MAX_REASONABLE_SPEED_KMH:
                point["segment_status"] = "suspicious"
                point["segment_reason"] = "impossible_speed"
                point["counted_for_km"] = False
                diagnostics["suspicious_segments"] += 1
            else:
                diagnostics["normal_segments"] += 1

        result.append(_public_point(point))
        previous = point

    return result, diagnostics


def _public_point(point: dict[str, Any]) -> dict[str, Any]:
    public = dict(point)
    public.pop("gps_at", None)
    return public


def local_date_for_point(point: dict[str, Any]) -> str | None:
    raw = point.get("gps_time") or point.get("timestamp") or point.get("received_at")
    parsed = parse_gps_datetime(raw)
    return parsed.astimezone(ECUADOR_TZ).date().isoformat() if parsed else None


def empty_mileage_day(day: date | str) -> dict[str, Any]:
    day_key = day.isoformat() if isinstance(day, date) else str(day)
    return {
        "date": day_key,
        "km": 0.0,
        "max_speed": 0.0,
        "points": 0,
        "ignition_on": 0,
        "ignition_off": 0,
        "initial_lat": None,
        "initial_lon": None,
        "initial_time": None,
        "final_lat": None,
        "final_lon": None,
        "final_time": None,
        "gap_segments": 0,
        "suspicious_segments": 0,
        "discarded_segments": 0,
    }


def summarize_daily_mileage(rows: Iterable[Any], from_d: date, to_d: date) -> list[dict[str, Any]]:
    route_points, diagnostics = build_route_points(rows)
    days: dict[str, dict[str, Any]] = {}
    previous_by_day: dict[str, dict[str, Any]] = {}

    for point in route_points:
        day_key = local_date_for_point(point)
        if not day_key or day_key < from_d.isoformat() or day_key > to_d.isoformat():
            continue
        entry = days.setdefault(day_key, empty_mileage_day(day_key))
        entry["points"] += 1
        entry["final_lat"] = point["lat"]
        entry["final_lon"] = point["lon"]
        entry["final_time"] = point.get("timestamp")
        if entry["initial_lat"] is None:
            entry["initial_lat"] = point["lat"]
            entry["initial_lon"] = point["lon"]
            entry["initial_time"] = point.get("timestamp")
        if point.get("speed") is not None and point["speed"] > entry["max_speed"]:
            entry["max_speed"] = point["speed"]
        if point.get("ignition") == "on":
            entry["ignition_on"] += 1
        elif point.get("ignition") == "off":
            entry["ignition_off"] += 1

        if point.get("segment_status") == "gap":
            entry["gap_segments"] += 1
            entry["discarded_segments"] += 1
        elif point.get("segment_status") == "suspicious":
            entry["suspicious_segments"] += 1
            entry["discarded_segments"] += 1
        elif point.get("counted_for_km") and previous_by_day.get(day_key):
            entry["km"] += float(point.get("distance_km") or 0.0)

        previous_by_day[day_key] = point

    result: list[dict[str, Any]] = []
    cur = from_d
    while cur <= to_d:
        day_entry = days.get(cur.isoformat(), empty_mileage_day(cur))
        day_entry["km"] = round(float(day_entry["km"]), 3)
        day_entry["diagnostics"] = diagnostics
        result.append(day_entry)
        cur += timedelta(days=1)
    return result


def point_in_geofence(lat: float, lon: float, geofence_type: str, geometry: dict[str, Any]) -> bool:
    kind = str(geofence_type or "").strip().lower()
    geom = geometry if isinstance(geometry, dict) else {}
    if kind == "circle":
        center = geom.get("center") if isinstance(geom.get("center"), dict) else {}
        center_lat = coerce_float(center.get("lat") or geom.get("lat"))
        center_lon = coerce_float(center.get("lon") or center.get("lng") or geom.get("lon") or geom.get("lng"))
        radius_m = coerce_float(geom.get("radius_m") or geom.get("radius") or geom.get("radio_m"))
        if center_lat is None or center_lon is None or radius_m is None:
            return False
        return haversine_km(lat, lon, center_lat, center_lon) * 1000 <= radius_m

    if kind == "polygon":
        coordinates = geom.get("coordinates") or []
        if (
            geom.get("type") == "Polygon"
            and str(geom.get("coordinate_order") or "").lower() != "latlon"
            and coordinates
            and isinstance(coordinates[0], list)
        ):
            coordinates = coordinates[0]
            points = [(coerce_float(p[1]), coerce_float(p[0])) for p in coordinates if isinstance(p, list) and len(p) >= 2]
        else:
            points = [
                (coerce_float(p.get("lat") if isinstance(p, dict) else (p[0] if isinstance(p, list) and len(p) >= 2 else None)),
                 coerce_float((p.get("lon") or p.get("lng")) if isinstance(p, dict) else (p[1] if isinstance(p, list) and len(p) >= 2 else None)))
                for p in coordinates
            ]
        polygon = [(p_lat, p_lon) for p_lat, p_lon in points if p_lat is not None and p_lon is not None]
        if len(polygon) < 3:
            return False
        inside = False
        j = len(polygon) - 1
        for i, (lat_i, lon_i) in enumerate(polygon):
            lat_j, lon_j = polygon[j]
            if ((lat_i > lat) != (lat_j > lat)) and (
                lon < (lon_j - lon_i) * (lat - lat_i) / ((lat_j - lat_i) or 1e-12) + lon_i
            ):
                inside = not inside
            j = i
        return inside

    return False
