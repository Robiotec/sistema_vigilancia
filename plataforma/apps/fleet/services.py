from __future__ import annotations

import re
import json
import time as monotonic_time
from dataclasses import dataclass
from datetime import date, datetime, time, timezone as datetime_timezone
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import OperationalError, ProgrammingError, connection
from django.db.models import OuterRef, Q, Subquery
from django.db.models import QuerySet
from django.utils import timezone

from apps.devices.models import Camera, Drone, Vehicle
from apps.fleet.models import DroneTelemetry, VehicleRouteSegment, VehicleTelemetry
from apps.streaming.models import StreamConfig, StreamPath
from apps.streaming.services import MediaMTXPath, StreamUrlBuilder

ROUTE_SEGMENT_MAX_GAP_SECONDS = 30 * 60
ROUTE_SEGMENT_MAX_DISTANCE_KM = 8
ROUTE_SEGMENT_MAX_SPEED_KMH = 180
RETRYABLE_OSRM_SEGMENT_REASONS = {"osrm_budget_deferred", "osrm_disabled"}


@dataclass(frozen=True)
class VehicleDistance:
    vehicle_id: str
    kilometers: float
    points: int


class VehicleKilometerService:
    def calculate(self, telemetry: QuerySet[VehicleTelemetry]) -> VehicleDistance | None:
        points = list(
            telemetry.exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .order_by("received_at")
        )
        if not points:
            return None

        kilometers = 0.0
        previous = None
        for point in points:
            if previous is not None:
                kilometers += self._haversine_km(
                    previous.latitude,
                    previous.longitude,
                    point.latitude,
                    point.longitude,
                )
            previous = point

        return VehicleDistance(
            vehicle_id=str(points[0].vehicle_id),
            kilometers=round(kilometers, 3),
            points=len(points),
        )

    def for_day(self, vehicle_id: str, start: datetime, end: datetime) -> VehicleDistance | None:
        telemetry = VehicleTelemetry.objects.filter(
            vehicle_id=vehicle_id,
            received_at__gte=start,
            received_at__lt=end,
        )
        return self.calculate(telemetry)

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0088
        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
        return 2 * radius_km * asin(sqrt(a))


class FleetMapService:
    def latest_locations(self, *, company_id: str | None = None, active_only: bool = True) -> dict[str, object]:
        base = self._valid_telemetry_queryset(company_id=company_id, active_only=active_only)
        rows = self._latest_rows(base)

        drone_base = self._valid_drone_telemetry_queryset(company_id=company_id, active_only=active_only)
        drone_rows = self._latest_drone_rows(drone_base)
        vehicle_camera_links, drone_camera_links = self._camera_links_for_devices(
            vehicle_ids=[str(row.vehicle_id) for row in rows if row.vehicle_id],
            drone_ids=[str(row.drone_id) for row in drone_rows if row.drone_id],
        )
        items = [
            self._latest_item(row, vehicle_camera_links)
            for row in rows
            if row.vehicle_id and row.vehicle
        ]
        items += [
            self._latest_drone_item(row, drone_camera_links)
            for row in drone_rows
            if row.drone_id and row.drone
        ]

        return {
            "count": len(items),
            "generated_at": timezone.now().isoformat(),
            "results": items,
        }

    def route_for_day(self, *, vehicle_id: str, target_day: date) -> dict[str, object]:
        vehicle = Vehicle.objects.get(id=vehicle_id)
        source_vehicle_ids = self._source_vehicle_ids(vehicle)
        local_tz = timezone.get_current_timezone()
        local_start = datetime.combine(target_day, time.min, tzinfo=local_tz)
        local_end = datetime.combine(target_day, time.max, tzinfo=local_tz)
        rows = (
            VehicleTelemetry.objects.filter(
                vehicle_id__in=source_vehicle_ids,
                received_at__gte=local_start.astimezone(datetime_timezone.utc),
                received_at__lte=local_end.astimezone(datetime_timezone.utc),
            )
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .order_by("received_at")
        )
        points = [self._route_point(row) for row in rows if self._valid_coordinates(row.latitude, row.longitude)]
        self._materialize_route_segment_rows(points, source_vehicle_ids=source_vehicle_ids, target_day=target_day)
        self._apply_route_segment_rows(points, source_vehicle_ids=source_vehicle_ids, target_day=target_day)
        segments, total_km = self._segments(points)
        return {
            "vehicle": self._vehicle_payload(vehicle, self._camera_links_for_vehicle(vehicle.id)),
            "source_vehicle_ids": [str(source_id) for source_id in source_vehicle_ids],
            "date": target_day.isoformat(),
            "total_points": len(points),
            "total_km": round(total_km, 3),
            "segments": segments,
            "points": points,
        }

    def route_for_day_drone(self, *, drone_id: str, target_day: date) -> dict[str, object]:
        drone = Drone.objects.get(id=drone_id)
        local_tz = timezone.get_current_timezone()
        local_start = datetime.combine(target_day, time.min, tzinfo=local_tz)
        local_end = datetime.combine(target_day, time.max, tzinfo=local_tz)
        rows = (
            DroneTelemetry.objects.filter(
                drone_id=drone.id,
                received_at__gte=local_start.astimezone(datetime_timezone.utc),
                received_at__lte=local_end.astimezone(datetime_timezone.utc),
            )
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .order_by("received_at")
        )
        points = [self._route_point(row) for row in rows if self._valid_coordinates(row.latitude, row.longitude)]
        segments, total_km = self._segments(points)
        return {
            "vehicle": self._drone_payload(drone, self._camera_links_for_drone(drone.id)),
            "source_vehicle_ids": [str(drone.id)],
            "date": target_day.isoformat(),
            "total_points": len(points),
            "total_km": round(total_km, 3),
            "segments": segments,
            "points": points,
        }

    def _valid_telemetry_queryset(self, *, company_id: str | None, active_only: bool) -> QuerySet[VehicleTelemetry]:
        queryset = (
            VehicleTelemetry.objects.exclude(vehicle_id__isnull=True)
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .filter(vehicle__deleted_at__isnull=True)
        )
        if active_only:
            queryset = queryset.filter(vehicle__active=True)
        if company_id:
            queryset = queryset.filter(vehicle__company_id=company_id)
        return queryset

    def _latest_rows(self, base: QuerySet[VehicleTelemetry]) -> list[VehicleTelemetry]:
        if connection.vendor == "postgresql":
            rows = list(
                base.select_related("vehicle", "vehicle__company")
                .order_by("vehicle_id", "-received_at")
                .distinct("vehicle_id")
            )
        else:
            latest_ids = (
                base.filter(vehicle_id=OuterRef("vehicle_id"))
                .order_by("-received_at")
                .values("id")[:1]
            )
            rows = list(
                base.filter(id=Subquery(latest_ids))
                .select_related("vehicle", "vehicle__company")
            )
        return sorted(self._dedupe_latest_rows(rows), key=lambda row: ((row.vehicle.plate or ""), row.vehicle.name))

    def _dedupe_latest_rows(self, rows: list[VehicleTelemetry]) -> list[VehicleTelemetry]:
        grouped: dict[str, VehicleTelemetry] = {}
        for row in rows:
            key = self._fleet_key(row.vehicle)
            current = grouped.get(key)
            if current is None or row.received_at > current.received_at:
                grouped[key] = row
        return list(grouped.values())

    def _source_vehicle_ids(self, vehicle: Vehicle) -> list[str]:
        fleet_key = self._fleet_key(vehicle)
        vehicles = Vehicle.objects.filter(company_id=vehicle.company_id, active=True)
        source_ids = [str(item.id) for item in vehicles if self._fleet_key(item) == fleet_key]
        return source_ids or [str(vehicle.id)]

    def _latest_item(
        self,
        telemetry: VehicleTelemetry,
        camera_links_by_vehicle: dict[str, list[dict[str, object]]],
    ) -> dict[str, object]:
        vehicle = telemetry.vehicle
        return {
            "kind": "vehicle",
            "vehicle": self._vehicle_payload(vehicle, camera_links_by_vehicle.get(str(vehicle.id), [])),
            "lat": telemetry.latitude,
            "lon": telemetry.longitude,
            "speed": telemetry.speed,
            "heading": telemetry.heading,
            "received_at": telemetry.received_at.isoformat(),
            "freshness": self._freshness(telemetry.received_at),
        }

    def _valid_drone_telemetry_queryset(self, *, company_id: str | None, active_only: bool) -> QuerySet[DroneTelemetry]:
        queryset = (
            DroneTelemetry.objects.exclude(drone_id__isnull=True)
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .filter(drone__deleted_at__isnull=True)
        )
        if active_only:
            queryset = queryset.filter(drone__active=True)
        if company_id:
            queryset = queryset.filter(drone__company_id=company_id)
        return queryset

    def _latest_drone_rows(self, base: QuerySet[DroneTelemetry]) -> list[DroneTelemetry]:
        if connection.vendor == "postgresql":
            rows = list(
                base.select_related("drone", "drone__company")
                .order_by("drone_id", "-received_at")
                .distinct("drone_id")
            )
        else:
            latest_ids = (
                base.filter(drone_id=OuterRef("drone_id"))
                .order_by("-received_at")
                .values("id")[:1]
            )
            rows = list(
                base.filter(id=Subquery(latest_ids))
                .select_related("drone", "drone__company")
            )
        return sorted(rows, key=lambda row: row.drone.name)

    def _latest_drone_item(
        self,
        telemetry: DroneTelemetry,
        camera_links_by_drone: dict[str, list[dict[str, object]]],
    ) -> dict[str, object]:
        drone = telemetry.drone
        return {
            "kind": "drone",
            "vehicle": self._drone_payload(drone, camera_links_by_drone.get(str(drone.id), [])),
            "lat": telemetry.latitude,
            "lon": telemetry.longitude,
            "speed": telemetry.speed,
            "heading": telemetry.heading,
            "received_at": telemetry.received_at.isoformat(),
            "freshness": self._freshness(telemetry.received_at),
        }

    @staticmethod
    def _drone_payload(drone: Drone, camera_links: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "id": str(drone.id),
            "company_id": str(drone.company_id),
            "name": drone.name,
            "plate": None,
            "unique_code": drone.unique_code,
            "driver_name": None,
            "vehicle_type": "dron",
            "vehicle_subtype": drone.drone_type,
            "active": drone.active,
            "cameras": camera_links or [],
        }

    def _route_point(self, telemetry: VehicleTelemetry | DroneTelemetry) -> dict[str, object]:
        source_id = getattr(telemetry, "vehicle_id", None) or getattr(telemetry, "drone_id", None)
        return {
            "id": str(telemetry.id),
            "source_vehicle_id": str(source_id) if source_id else None,
            "lat": telemetry.latitude,
            "lon": telemetry.longitude,
            "speed": telemetry.speed,
            "heading": telemetry.heading,
            "received_at": telemetry.received_at.isoformat(),
            "segment_status": "start",
            "segment_reason": None,
            "distance_km": 0.0,
            "elapsed_seconds": 0.0,
            "implied_speed_kmh": 0.0,
            "counted_for_km": False,
            "segment_geometry": [],
        }

    def _segments(self, points: list[dict[str, object]]) -> tuple[list[list[dict[str, object]]], float]:
        segments: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        total_km = 0.0
        previous: dict[str, object] | None = None

        for point in points:
            if previous is None:
                self._set_start_metadata(point)
                current.append(point)
                previous = point
                continue

            metrics = self._segment_metrics(previous, point)
            self._ensure_segment_metadata(previous, point, metrics)
            status = str(point.get("segment_status") or metrics["segment_status"]).lower()
            if status in {"gap", "suspicious"}:
                if current:
                    segments.append(current)
                current = [point]
            else:
                total_km += float(point.get("distance_km") or metrics["distance_km"] or 0.0)
                current.append(point)
            previous = point

        if current:
            segments.append(current)
        return segments, total_km

    def _segment_metrics(self, previous: dict[str, object], point: dict[str, object]) -> dict[str, object]:
        elapsed = self._elapsed_seconds(previous, point)
        distance = self._point_distance_km(previous, point)
        speed = (distance / elapsed * 3600) if elapsed > 0 else 0
        if elapsed <= 0:
            status = "suspicious"
            reason = "non_increasing_gps_time"
            counted = False
        elif elapsed > ROUTE_SEGMENT_MAX_GAP_SECONDS:
            status = "gap"
            reason = "large_time_gap"
            counted = False
        elif distance > ROUTE_SEGMENT_MAX_DISTANCE_KM:
            status = "gap"
            reason = "large_distance_gap"
            counted = False
        elif speed > ROUTE_SEGMENT_MAX_SPEED_KMH:
            status = "suspicious"
            reason = "impossible_speed"
            counted = False
        else:
            status = "normal"
            reason = None
            counted = True
        return {
            "segment_status": status,
            "segment_reason": reason,
            "distance_km": distance,
            "elapsed_seconds": elapsed,
            "implied_speed_kmh": speed,
            "counted_for_km": counted,
        }

    def _ensure_segment_metadata(
        self,
        previous: dict[str, object],
        point: dict[str, object],
        metrics: dict[str, object],
    ) -> None:
        existing_status = str(point.get("segment_status") or "").lower()
        if not existing_status or existing_status == "start":
            point.update(metrics)
        for key in ("distance_km", "elapsed_seconds", "implied_speed_kmh"):
            if point.get(key) is None:
                point[key] = metrics[key]
        if point.get("counted_for_km") is None:
            point["counted_for_km"] = str(point.get("segment_status") or "").lower() in {"normal", "osrm", "raw"}
        if not point.get("segment_geometry"):
            point["segment_geometry"] = [
                [float(previous["lat"]), float(previous["lon"])],
                [float(point["lat"]), float(point["lon"])],
            ]

    @staticmethod
    def _set_start_metadata(point: dict[str, object]) -> None:
        point["segment_status"] = "start"
        point["segment_reason"] = None
        point["distance_km"] = 0.0
        point["elapsed_seconds"] = 0.0
        point["implied_speed_kmh"] = 0.0
        point["counted_for_km"] = False
        point["segment_geometry"] = []

    def _materialize_route_segment_rows(
        self,
        points: list[dict[str, object]],
        *,
        source_vehicle_ids: list[str],
        target_day: date,
    ) -> None:
        if len(points) < 2 or not self._route_segment_table_exists():
            return
        point_ids = [str(point["id"]) for point in points[1:] if point.get("id")]
        if not point_ids:
            return

        try:
            existing_rows = VehicleRouteSegment.objects.filter(
                vehicle_id__in=source_vehicle_ids,
                local_day=target_day,
                to_telemetry_id__in=point_ids,
            )
            by_to_id = {str(row.to_telemetry_id): row for row in existing_rows}
        except (OperationalError, ProgrammingError):
            return

        osrm_base_url = str(getattr(settings, "OSRM_BASE_URL", "") or "").strip().rstrip("/")
        osrm_remaining = max(0, int(getattr(settings, "OSRM_MAX_SEGMENTS_PER_REQUEST", 0) or 0))
        osrm_timeout = max(0.2, min(1.0, float(getattr(settings, "OSRM_REQUEST_TIMEOUT_SECONDS", 0.8) or 0.8)))
        osrm_deadline = monotonic_time.monotonic() + max(
            0.5,
            float(getattr(settings, "OSRM_REQUEST_BUDGET_SECONDS", 6.0) or 6.0),
        )

        for index in range(1, len(points)):
            previous = points[index - 1]
            point = points[index]
            to_id = str(point.get("id") or "")
            from_id = str(previous.get("id") or "")
            if not to_id or not from_id:
                continue
            existing = by_to_id.get(to_id)
            can_retry_existing = existing and self._route_segment_can_retry_osrm(existing)
            if existing and not can_retry_existing:
                continue

            metrics = self._segment_metrics(previous, point)
            can_try_osrm = (
                bool(osrm_base_url)
                and osrm_remaining > 0
                and monotonic_time.monotonic() < osrm_deadline
                and metrics["segment_status"] not in {"gap", "suspicious"}
            )
            segment = self._build_route_segment(
                previous,
                point,
                metrics=metrics,
                osrm_base_url=osrm_base_url if can_try_osrm else "",
                osrm_timeout=osrm_timeout,
            )
            if can_try_osrm:
                osrm_remaining -= 1
            elif segment["segment_kind"] == "raw":
                segment["segment_reason"] = "osrm_budget_deferred" if osrm_base_url else "osrm_disabled"

            try:
                if existing:
                    self._update_route_segment_row(existing, segment)
                else:
                    row = VehicleRouteSegment(
                        vehicle_id=str(point.get("source_vehicle_id") or source_vehicle_ids[0]),
                        from_telemetry_id=from_id,
                        to_telemetry_id=to_id,
                        local_day=target_day,
                    )
                    self._update_route_segment_row(row, segment)
                    by_to_id[to_id] = row
            except (OperationalError, ProgrammingError):
                return

    def _build_route_segment(
        self,
        previous: dict[str, object],
        point: dict[str, object],
        *,
        metrics: dict[str, object],
        osrm_base_url: str,
        osrm_timeout: float,
    ) -> dict[str, object]:
        status = str(metrics["segment_status"])
        raw_geometry = self._raw_segment_geometry(previous, point)
        if status in {"gap", "suspicious"}:
            return {
                "segment_kind": "suspicious",
                "segment_reason": metrics["segment_reason"],
                "distance_km": metrics["distance_km"],
                "elapsed_seconds": metrics["elapsed_seconds"],
                "implied_speed_kmh": metrics["implied_speed_kmh"],
                "confidence": None,
                "geometry": raw_geometry,
            }

        matched = self._match_segment_with_osrm(
            previous,
            point,
            osrm_base_url=osrm_base_url,
            timeout_seconds=osrm_timeout,
        )
        if matched:
            matched.update({
                "elapsed_seconds": metrics["elapsed_seconds"],
                "implied_speed_kmh": metrics["implied_speed_kmh"],
            })
            return matched

        return {
            "segment_kind": "raw",
            "segment_reason": "osrm_no_match" if osrm_base_url else "osrm_disabled",
            "distance_km": metrics["distance_km"],
            "elapsed_seconds": metrics["elapsed_seconds"],
            "implied_speed_kmh": metrics["implied_speed_kmh"],
            "confidence": None,
            "geometry": raw_geometry,
        }

    def _update_route_segment_row(self, row: VehicleRouteSegment, segment: dict[str, object]) -> None:
        row.segment_kind = str(segment["segment_kind"])
        row.segment_reason = segment.get("segment_reason") or None
        row.distance_km = float(segment.get("distance_km") or 0.0)
        row.elapsed_seconds = float(segment.get("elapsed_seconds") or 0.0)
        row.implied_speed_kmh = float(segment.get("implied_speed_kmh") or 0.0)
        row.confidence = segment.get("confidence")
        row.geometry = {
            "type": "LineString",
            "coordinate_order": "latlon",
            "coordinates": segment.get("geometry") or [],
        }
        row.save()

    @staticmethod
    def _route_segment_can_retry_osrm(segment: VehicleRouteSegment) -> bool:
        return (
            str(segment.segment_kind or "").lower() == "raw"
            and str(segment.segment_reason or "").lower() in RETRYABLE_OSRM_SEGMENT_REASONS
        )

    @staticmethod
    def _raw_segment_geometry(previous: dict[str, object], point: dict[str, object]) -> list[list[float]]:
        return [
            [float(previous["lat"]), float(previous["lon"])],
            [float(point["lat"]), float(point["lon"])],
        ]

    def _match_segment_with_osrm(
        self,
        previous: dict[str, object],
        point: dict[str, object],
        *,
        osrm_base_url: str,
        timeout_seconds: float,
    ) -> dict[str, object] | None:
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
            payload = self._osrm_json(url, timeout_seconds)
        except (OSError, ValueError, TimeoutError):
            return self._route_segment_with_osrm(previous, point, osrm_base_url=base_url, timeout_seconds=timeout_seconds)

        if payload.get("code") == "Ok":
            matchings = payload.get("matchings")
            matching = matchings[0] if isinstance(matchings, list) and matchings and isinstance(matchings[0], dict) else {}
            confidence = self._float_or(matching.get("confidence"), 0.0)
            geometry = matching.get("geometry") if isinstance(matching.get("geometry"), dict) else {}
            latlon = self._osrm_coordinates_to_latlon(geometry.get("coordinates"))
            if confidence >= float(getattr(settings, "OSRM_MATCH_CONFIDENCE_MIN", 0.55) or 0.55) and len(latlon) >= 2:
                return {
                    "segment_kind": "osrm",
                    "segment_reason": None,
                    "confidence": confidence,
                    "distance_km": self._float_or(matching.get("distance"), 0.0) / 1000.0,
                    "geometry": latlon,
                }

        return self._route_segment_with_osrm(previous, point, osrm_base_url=base_url, timeout_seconds=timeout_seconds)

    def _route_segment_with_osrm(
        self,
        previous: dict[str, object],
        point: dict[str, object],
        *,
        osrm_base_url: str,
        timeout_seconds: float,
    ) -> dict[str, object] | None:
        base_url = str(osrm_base_url or "").strip().rstrip("/")
        if not base_url:
            return None
        coords = f"{previous['lon']},{previous['lat']};{point['lon']},{point['lat']}"
        path = quote(coords, safe=",;")
        url = f"{base_url}/route/v1/driving/{path}?geometries=geojson&overview=full&steps=false"
        try:
            payload = self._osrm_json(url, timeout_seconds)
        except (OSError, ValueError, TimeoutError):
            return None

        if payload.get("code") != "Ok":
            return None
        routes = payload.get("routes")
        route = routes[0] if isinstance(routes, list) and routes and isinstance(routes[0], dict) else {}
        geometry = route.get("geometry") if isinstance(route.get("geometry"), dict) else {}
        latlon = self._osrm_coordinates_to_latlon(geometry.get("coordinates"))
        if len(latlon) < 2:
            return None
        distance_km = self._float_or(route.get("distance"), 0.0) / 1000.0
        raw_distance_km = self._point_distance_km(previous, point)
        if distance_km <= 0 or (raw_distance_km > 0 and distance_km > max(raw_distance_km * 4, raw_distance_km + 2.0)):
            return None
        return {
            "segment_kind": "osrm",
            "segment_reason": "route_fallback",
            "confidence": None,
            "distance_km": distance_km,
            "geometry": latlon,
        }

    @staticmethod
    def _osrm_json(url: str, timeout_seconds: float) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": "RobiotecFleet/1.0"})
        with urlopen(request, timeout=max(0.2, timeout_seconds)) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _float_or(value: object, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _osrm_coordinates_to_latlon(coordinates: object) -> list[list[float]]:
        result: list[list[float]] = []
        if not isinstance(coordinates, list):
            return result
        for coordinate in coordinates:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            try:
                lon = float(coordinate[0])
                lat = float(coordinate[1])
            except (TypeError, ValueError):
                continue
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                result.append([lat, lon])
        return result

    def _apply_route_segment_rows(
        self,
        points: list[dict[str, object]],
        *,
        source_vehicle_ids: list[str],
        target_day: date,
    ) -> None:
        if len(points) < 2 or not self._route_segment_table_exists():
            return
        point_ids = [str(point["id"]) for point in points[1:] if point.get("id")]
        if not point_ids:
            return
        try:
            rows = VehicleRouteSegment.objects.filter(
                vehicle_id__in=source_vehicle_ids,
                local_day=target_day,
                to_telemetry_id__in=point_ids,
            )
            by_to_id = {str(row.to_telemetry_id): row for row in rows}
        except (OperationalError, ProgrammingError):
            return
        for point in points[1:]:
            segment = by_to_id.get(str(point["id"]))
            if segment:
                self._apply_route_segment_row(point, segment)

    def _apply_route_segment_row(self, point: dict[str, object], segment: VehicleRouteSegment) -> None:
        status = str(segment.segment_kind or "raw").lower()
        point["segment_status"] = status
        point["segment_reason"] = segment.segment_reason
        point["distance_km"] = float(segment.distance_km or 0.0)
        point["elapsed_seconds"] = float(segment.elapsed_seconds or 0.0)
        point["implied_speed_kmh"] = float(segment.implied_speed_kmh or 0.0)
        point["counted_for_km"] = status in {"osrm", "raw", "normal"}
        point["segment_geometry"] = self._segment_geometry_latlon(segment.geometry)

    def _route_segment_table_exists(self) -> bool:
        return VehicleRouteSegment._meta.db_table in connection.introspection.table_names()

    def _segment_geometry_latlon(self, geometry: object) -> list[list[float]]:
        if not isinstance(geometry, dict):
            return []
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            return []
        coordinate_order = str(geometry.get("coordinate_order") or "").lower()
        result: list[list[float]] = []
        for coordinate in coordinates:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            try:
                first = float(coordinate[0])
                second = float(coordinate[1])
            except (TypeError, ValueError):
                continue
            lat, lon = (first, second) if coordinate_order == "latlon" else (second, first)
            if self._valid_coordinates(lat, lon):
                result.append([lat, lon])
        return result

    def _point_distance_km(self, previous: dict[str, object], point: dict[str, object]) -> float:
        return VehicleKilometerService._haversine_km(
            float(previous["lat"]),
            float(previous["lon"]),
            float(point["lat"]),
            float(point["lon"]),
        )

    @staticmethod
    def _elapsed_seconds(previous: dict[str, object], point: dict[str, object]) -> float:
        previous_at = datetime.fromisoformat(str(previous["received_at"]))
        point_at = datetime.fromisoformat(str(point["received_at"]))
        return max((point_at - previous_at).total_seconds(), 0.0)

    @staticmethod
    def _valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
        if latitude is None or longitude is None:
            return False
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    @staticmethod
    def _vehicle_payload(vehicle: Vehicle, camera_links: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "id": str(vehicle.id),
            "company_id": str(vehicle.company_id),
            "name": vehicle.name,
            "plate": vehicle.plate,
            "unique_code": vehicle.unique_code,
            "driver_name": vehicle.driver_name,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "vehicle_type": vehicle.vehicle_type,
            "vehicle_subtype": vehicle.vehicle_subtype,
            "active": vehicle.active,
            "cameras": camera_links or [],
        }

    def _camera_links_for_vehicle(self, vehicle_id: object) -> list[dict[str, object]]:
        vehicle_links, _ = self._camera_links_for_devices(vehicle_ids=[str(vehicle_id)], drone_ids=[])
        return vehicle_links.get(str(vehicle_id), [])

    def _camera_links_for_drone(self, drone_id: object) -> list[dict[str, object]]:
        _, drone_links = self._camera_links_for_devices(vehicle_ids=[], drone_ids=[str(drone_id)])
        return drone_links.get(str(drone_id), [])

    def _camera_links_for_devices(
        self,
        *,
        vehicle_ids: list[str],
        drone_ids: list[str],
    ) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
        vehicle_ids = [item for item in vehicle_ids if item]
        drone_ids = [item for item in drone_ids if item]
        if not vehicle_ids and not drone_ids:
            return {}, {}

        resource_filter = Q()
        if vehicle_ids:
            resource_filter |= Q(vehicle_id__in=vehicle_ids)
        if drone_ids:
            resource_filter |= Q(drone_id__in=drone_ids)
        queryset = Camera.objects.filter(active=True).filter(resource_filter)
        cameras = list(queryset.order_by("name"))
        if not cameras:
            return {}, {}
        stream_by_camera = self._stream_configs_by_camera([camera.id for camera in cameras])
        stream_paths_by_camera = self._stream_paths_by_camera([camera.id for camera in cameras])
        online_paths = self._online_mediamtx_paths()

        by_vehicle: dict[str, list[dict[str, object]]] = {}
        by_drone: dict[str, list[dict[str, object]]] = {}
        for camera in cameras:
            stream = stream_by_camera.get(camera.id)
            stream_path = stream_paths_by_camera.get(camera.id)
            path = self._camera_path(camera, stream, stream_path)
            ready = online_paths.get(path).ready if path in online_paths else False
            link = {
                "id": str(camera.id),
                "name": camera.name,
                "camera_type": camera.camera_type,
                "inference_type": camera.inference_type or "inactiva",
                "path": path,
                "online": bool(ready),
                "viewer_url": StreamUrlBuilder.viewer_url(path) if path else "",
                "whep_url": StreamUrlBuilder.whep_url(path) if path else "",
            }
            if camera.vehicle_id:
                by_vehicle.setdefault(str(camera.vehicle_id), []).append(link)
            if camera.drone_id:
                by_drone.setdefault(str(camera.drone_id), []).append(link)
        return by_vehicle, by_drone

    @staticmethod
    def _stream_configs_by_camera(camera_ids: list[object]) -> dict[object, StreamConfig]:
        queryset = StreamConfig.objects.filter(active=True, camera_id__in=camera_ids).order_by("-updated_at", "mediamtx_path")
        result = {}
        for stream in queryset:
            result.setdefault(stream.camera_id, stream)
        return result

    @staticmethod
    def _stream_paths_by_camera(camera_ids: list[object]) -> dict[object, StreamPath]:
        queryset = StreamPath.objects.filter(active=True, resource_type="camera", resource_id__in=camera_ids).order_by("path")
        result = {}
        for stream_path in queryset:
            result.setdefault(stream_path.resource_id, stream_path)
        return result

    @staticmethod
    def _camera_path(camera: Camera, stream: StreamConfig | None, stream_path: StreamPath | None) -> str:
        return str(
            (stream.mediamtx_path if stream else "")
            or (stream.publish_path if stream else "")
            or (stream_path.path if stream_path else "")
            or camera.unique_code
            or camera.name
            or ""
        ).strip().strip("/")

    def _online_mediamtx_paths(self) -> dict[str, MediaMTXPath]:
        try:
            from apps.streaming.services import MediaMTXClient

            result = MediaMTXClient(timeout=2.0).list_paths()
        except Exception:
            return {}
        return {item.name: item for item in result.value} if result.ok and result.value else {}

    @staticmethod
    def _fleet_key(vehicle: Vehicle) -> str:
        raw = str(vehicle.plate or vehicle.name or vehicle.unique_code or vehicle.id).upper()
        plate_match = re.search(r"([A-Z]{2,4})[ -]?([0-9]{3,5})", raw)
        if plate_match:
            return f"{plate_match.group(1)}{plate_match.group(2)}"
        normalized = re.sub(r"[^A-Z0-9]", "", raw)
        return normalized or str(vehicle.id)

    @staticmethod
    def _freshness(received_at: datetime) -> str:
        age_seconds = (timezone.now() - received_at).total_seconds()
        return "online" if age_seconds <= 3600 else "stale"
