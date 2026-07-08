from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.utils import timezone

from apps.alerts.models import NotificationEmailRecipient
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Vehicle
from apps.fleet.models import VehicleTelemetry
from apps.geofences.models import Geofence, GeofenceAlert
from apps.organizations.models import Company
from apps.reports.services import DailyFleetReportService, FleetReportSettingsService


class DailyFleetReportServiceTests(LegacySchemaTestCase):
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
            vehicle_subtype="camioneta",
            driver_name="Chofer Uno",
            active=True,
            can_publish=True,
        )
        self.duplicate = Vehicle.objects.create(
            company=self.company,
            name="ABC 123 duplicado",
            plate="ABC 123",
            unique_code="GPS-001-B",
            vehicle_type="auto",
            vehicle_subtype="camioneta",
            driver_name="Chofer Uno",
            active=True,
            can_publish=True,
        )
        self.report_date = timezone.localdate()

    def test_report_deduplicates_vehicle_and_counts_geofence_interval(self):
        first_at = self._local_datetime(self.report_date, 8, 0)
        second_at = first_at + timedelta(minutes=10)
        VehicleTelemetry.objects.create(
            vehicle=self.vehicle,
            latitude=-0.1807,
            longitude=-78.4678,
            speed=10,
            received_at=first_at,
        )
        VehicleTelemetry.objects.create(
            vehicle=self.duplicate,
            latitude=-0.1900,
            longitude=-78.4700,
            speed=20,
            received_at=second_at,
        )
        geofence = Geofence.objects.create(
            company=self.company,
            name="Patio Norte",
            geofence_type="polygon",
            geometry={"type": "Polygon", "coordinates": []},
            active=True,
        )
        GeofenceAlert.objects.create(
            vehicle=self.vehicle,
            plate="ABC123",
            geofence=geofence,
            geofence_name=geofence.name,
            event_type="entry",
            gps_at=first_at,
            recorded_at=first_at,
        )
        GeofenceAlert.objects.create(
            vehicle=self.duplicate,
            plate="ABC123",
            geofence=geofence,
            geofence_name=geofence.name,
            event_type="exit",
            gps_at=first_at + timedelta(hours=1),
            recorded_at=first_at + timedelta(hours=1),
        )

        report = DailyFleetReportService().build(self.report_date)

        self.assertEqual(report.totals["total_vehicles"], 1)
        self.assertEqual(report.totals["active_vehicles"], 1)
        self.assertEqual(report.totals["geofence_intervals"], 1)
        self.assertEqual(report.vehicles[0]["source_count"], 2)
        self.assertEqual(report.vehicles[0]["brand"], "SUZUKI")
        self.assertEqual(report.vehicles[0]["model"], "GRAND VITARA")
        self.assertEqual(report.vehicles[0]["year"], 2012)
        self.assertEqual(report.vehicles[0]["geofence_intervals"][0]["duration_minutes"], 60)
        self.assertGreater(report.vehicles[0]["total_km"], 0)

    def test_geofence_intervals_are_chronological(self):
        early_at = self._local_datetime(self.report_date, 8, 0)
        later_at = self._local_datetime(self.report_date, 10, 0)
        early_geofence = Geofence.objects.create(
            company=self.company,
            name="Zona Temprana",
            geofence_type="polygon",
            geometry={"type": "Polygon", "coordinates": []},
            active=True,
        )
        later_geofence = Geofence.objects.create(
            company=self.company,
            name="Zona Tarde",
            geofence_type="polygon",
            geometry={"type": "Polygon", "coordinates": []},
            active=True,
        )
        GeofenceAlert.objects.create(
            vehicle=self.vehicle,
            plate="ABC123",
            geofence=later_geofence,
            geofence_name=later_geofence.name,
            event_type="entry",
            gps_at=later_at,
            recorded_at=later_at,
        )
        GeofenceAlert.objects.create(
            vehicle=self.vehicle,
            plate="ABC123",
            geofence=later_geofence,
            geofence_name=later_geofence.name,
            event_type="exit",
            gps_at=later_at + timedelta(minutes=20),
            recorded_at=later_at + timedelta(minutes=20),
        )
        GeofenceAlert.objects.create(
            vehicle=self.duplicate,
            plate="ABC123",
            geofence=early_geofence,
            geofence_name=early_geofence.name,
            event_type="entry",
            gps_at=early_at,
            recorded_at=early_at,
        )
        GeofenceAlert.objects.create(
            vehicle=self.duplicate,
            plate="ABC123",
            geofence=early_geofence,
            geofence_name=early_geofence.name,
            event_type="exit",
            gps_at=early_at + timedelta(minutes=20),
            recorded_at=early_at + timedelta(minutes=20),
        )

        report = DailyFleetReportService().build(self.report_date)

        self.assertEqual([row["geofence_name"] for row in report.geofence_intervals], ["Zona Temprana", "Zona Tarde"])

    def test_geofence_intervals_merge_devices_and_remove_overlaps(self):
        previous_day = self.report_date - timedelta(days=1)
        midnightish = self._local_datetime(previous_day, 23, 30)
        mina_exit_primary = self._local_datetime(self.report_date, 7, 58)
        mina_exit_backup = self._local_datetime(self.report_date, 8, 16)
        san_miguel_entry = self._local_datetime(self.report_date, 8, 30)
        san_miguel_exit = self._local_datetime(self.report_date, 8, 42)
        stale_exit = self._local_datetime(self.report_date, 11, 16)
        mina = self._geofence("MINA TENGEL #1")
        camilo = self._geofence("CAMILO PONCE ENRIQUEZ")
        cambio = self._geofence("EL CAMBIO")
        san_miguel = self._geofence("SAN MIGUEL DE BRASIL")

        self._alert(self.vehicle, mina, "entry", midnightish)
        self._alert(self.duplicate, mina, "entry", midnightish)
        self._alert(self.vehicle, camilo, "entry", midnightish)
        self._alert(self.vehicle, cambio, "entry", midnightish)
        self._alert(self.vehicle, mina, "exit", mina_exit_primary)
        self._alert(self.duplicate, mina, "exit", mina_exit_backup)
        self._alert(self.vehicle, camilo, "exit", stale_exit)
        self._alert(self.vehicle, cambio, "exit", stale_exit + timedelta(hours=1))
        self._alert(self.vehicle, san_miguel, "entry", san_miguel_entry)
        self._alert(self.vehicle, san_miguel, "exit", san_miguel_exit)

        report = DailyFleetReportService().build(self.report_date)

        self.assertEqual([row["geofence_name"] for row in report.geofence_intervals], ["MINA TENGEL #1", "SAN MIGUEL DE BRASIL"])
        self.assertEqual(report.geofence_intervals[0]["duration_minutes"], 496)

    def test_settings_normalize_recipients_and_send_uses_them(self):
        NotificationEmailRecipient.objects.create(email="fallback@example.com", active=True)
        saved = FleetReportSettingsService().save(
            {
                "enabled": True,
                "send_time": "06:30",
                "recipients": ["ops@example.com", "ops@example.com", "bad"],
            }
        )
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["send_time"], "06:30")
        self.assertEqual(saved["recipients"], ["ops@example.com"])

        with patch("apps.reports.services.EmailSender.send", return_value=["ops@example.com"]) as send:
            result = DailyFleetReportService().send_for_date(self.report_date, mark_sent=True)

        self.assertEqual(result["total"], 1)
        self.assertEqual(send.call_args.args[0]["recipients"], ["ops@example.com"])
        self.assertEqual(FleetReportSettingsService().load()["last_sent_date"], self.report_date.isoformat())

    def test_pdf_builder_returns_pdf_bytes(self):
        report = DailyFleetReportService().build(self.report_date)

        pdf = DailyFleetReportService().build_pdf(report)

        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"Reporte diario de flota", pdf)
        self.assertIn(b"/MediaBox [0 0 842 595]", pdf)
        self.assertIn(b"A\xf1o", pdf)
        self.assertIn(b"SUZUKI", pdf)
        self.assertIn(b"GRAND VITARA", pdf)
        self.assertIn(b"2012", pdf)

    @staticmethod
    def _local_datetime(day, hour: int, minute: int):
        local_tz = timezone.get_current_timezone()
        local_value = datetime.combine(day, time(hour, minute), tzinfo=local_tz)
        return local_value.astimezone(datetime_timezone.utc)

    def _geofence(self, name: str):
        return Geofence.objects.create(
            company=self.company,
            name=name,
            geofence_type="polygon",
            geometry={"type": "Polygon", "coordinates": []},
            active=True,
        )

    @staticmethod
    def _alert(vehicle, geofence, event_type: str, at):
        return GeofenceAlert.objects.create(
            vehicle=vehicle,
            plate=vehicle.plate or "",
            geofence=geofence,
            geofence_name=geofence.name,
            event_type=event_type,
            gps_at=at,
            recorded_at=at,
        )
