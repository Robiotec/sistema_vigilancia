from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as datetime_timezone

from django.test import override_settings
from django.utils import timezone

from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Camera, Vehicle
from apps.fleet.models import VehicleRouteSegment, VehicleTelemetry
from apps.fleet.services import FleetMapService
from apps.organizations.models import Company
from apps.streaming.models import StreamConfig
from apps.streaming.services import MediaMTXPath


@override_settings(OSRM_BASE_URL="", OSRM_MAX_SEGMENTS_PER_REQUEST=0)
class FleetMapServiceTests(LegacySchemaTestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa Test", active=True)
        self.vehicle = Vehicle.objects.create(
            company=self.company,
            name="Unidad 01",
            plate="ABC123",
            unique_code="GPS-001",
            brand="SUZUKI",
            model="GRAND VITARA",
            year=2012,
            vehicle_type="auto",
            active=True,
            can_publish=True,
        )

    def test_latest_locations_returns_newest_point_per_vehicle(self):
        day = timezone.localdate()
        first_at = self._local_datetime(day, 8, 0)
        last_at = first_at + timedelta(minutes=10)
        duplicate = Vehicle.objects.create(
            company=self.company,
            name="ABC 123 duplicado",
            plate="ABC 123",
            unique_code="GPS-001-B",
            vehicle_type="auto",
            active=True,
            can_publish=True,
        )
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            speed=10,
            received_at=first_at,
        )
        VehicleTelemetry.objects.create(
            vehicle=duplicate,
            latitude=-0.1810,
            longitude=-78.4681,
            speed=18,
            received_at=last_at,
        )

        payload = FleetMapService().latest_locations(company_id=str(self.company.id))

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["vehicle"]["plate"], "ABC 123")
        self.assertEqual(payload["results"][0]["vehicle"]["brand"], "SUZUKI")
        self.assertEqual(payload["results"][0]["vehicle"]["model"], "GRAND VITARA")
        self.assertEqual(payload["results"][0]["vehicle"]["year"], 2012)
        self.assertEqual(payload["results"][0]["speed"], 18)

    def test_route_for_day_splits_unrealistic_jump(self):
        day = timezone.localdate()
        first_at = self._local_datetime(day, 9, 0)
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            received_at=first_at,
        )
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1810,
            longitude=-78.4680,
            received_at=first_at + timedelta(minutes=5),
        )
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-1.0,
            longitude=-79.0,
            received_at=first_at + timedelta(minutes=10),
        )

        payload = FleetMapService().route_for_day(vehicle_id=str(self.vehicle.id), target_day=day)

        self.assertEqual(payload["total_points"], 3)
        self.assertEqual(len(payload["segments"]), 2)
        self.assertEqual(payload["points"][2]["segment_status"], "gap")
        self.assertEqual(payload["points"][2]["segment_reason"], "large_distance_gap")
        self.assertLess(payload["total_km"], 1)

    def test_route_for_day_includes_existing_osrm_segment_geometry(self):
        day = timezone.localdate()
        first_at = self._local_datetime(day, 9, 0)
        first = VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            received_at=first_at,
        )
        second = VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1810,
            longitude=-78.4680,
            received_at=first_at + timedelta(minutes=5),
        )
        VehicleRouteSegment.objects.create(
            vehicle=self.vehicle,
            from_telemetry=first,
            to_telemetry=second,
            local_day=day,
            segment_kind="osrm",
            segment_reason=None,
            distance_km=0.42,
            elapsed_seconds=300,
            implied_speed_kmh=5.04,
            geometry={
                "type": "LineString",
                "coordinate_order": "latlon",
                "coordinates": [[-0.1807, -78.4678], [-0.1808, -78.4679], [-0.1810, -78.4680]],
            },
        )

        payload = FleetMapService().route_for_day(vehicle_id=str(self.vehicle.id), target_day=day)

        self.assertEqual(payload["points"][1]["segment_status"], "osrm")
        self.assertEqual(payload["points"][1]["segment_geometry"][1], [-0.1808, -78.4679])
        self.assertAlmostEqual(payload["total_km"], 0.42)

    def test_route_for_day_merges_duplicate_source_ids(self):
        duplicate = Vehicle.objects.create(
            company=self.company,
            name="ABC 123 duplicado",
            plate="ABC 123",
            unique_code="GPS-001-B",
            vehicle_type="auto",
            active=True,
            can_publish=True,
        )
        day = timezone.localdate()
        first_at = self._local_datetime(day, 10, 0)
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            received_at=first_at,
        )
        VehicleTelemetry.objects.create(
            vehicle=duplicate,
            latitude=-0.1810,
            longitude=-78.4680,
            received_at=first_at + timedelta(minutes=5),
        )

        payload = FleetMapService().route_for_day(vehicle_id=str(self.vehicle.id), target_day=day)

        self.assertEqual(payload["total_points"], 2)
        self.assertEqual(len(payload["source_vehicle_ids"]), 2)

    def test_latest_locations_includes_linked_camera_capability(self):
        day = timezone.localdate()
        Camera.objects.create(
            company=self.company,
            vehicle=self.vehicle,
            name="Cabina 01",
            brand="dahua",
            unique_code="CAM-VEH-001",
            camera_type="mobile",
            inference_type="inactiva",
            status="activo",
            active=True,
            can_publish=True,
        )
        StreamConfig.objects.create(
            camera=Camera.objects.get(unique_code="CAM-VEH-001"),
            mediamtx_path="CAM-VEH-001",
            input_protocol="rtsp",
            stream_status="activo",
            active=True,
            webrtc_enabled=True,
        )
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            speed=10,
            received_at=self._local_datetime(day, 11, 0),
        )
        service = FleetMapService()
        service._online_mediamtx_paths = lambda: {  # type: ignore[method-assign]
            "CAM-VEH-001": MediaMTXPath(name="CAM-VEH-001", ready=True, source="publisher")
        }

        payload = service.latest_locations(company_id=str(self.company.id))

        cameras = payload["results"][0]["vehicle"]["cameras"]
        self.assertEqual(cameras[0]["name"], "Cabina 01")
        self.assertTrue(cameras[0]["online"])
        self.assertTrue(str(cameras[0]["whep_url"]).endswith("/mediamtx/CAM-VEH-001/whep"))

    @staticmethod
    def _local_datetime(day, hour: int, minute: int):
        local_tz = timezone.get_current_timezone()
        local_value = datetime.combine(day, time(hour, minute), tzinfo=local_tz)
        return local_value.astimezone(datetime_timezone.utc)
