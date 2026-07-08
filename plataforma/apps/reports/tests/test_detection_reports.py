from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from apps.alerts.models import CameraEventHistory
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Camera
from apps.organizations.models import Company
from apps.reports.analytics import DetectionReportService


class DetectionReportServiceTests(LegacySchemaTestCase):
    def test_overview_daily_sessions_monthly_and_plates(self):
        company = Company.objects.create(name="Robiotec", active=True)
        Camera.objects.create(company=company, name="Acceso", brand="dahua", unique_code="CAM-001", active=True)
        self._event("p1", "person", "CAM-001", "2026-07-01T08:00:00", person_id="094", person_name="Ana")
        self._event("p2", "person", "CAM-001", "2026-07-01T08:10:00", person_id="094", person_name="Ana")
        self._event("p3", "person", "CAM-001", "2026-07-01T10:00:00", person_id="094", person_name="Ana")
        self._event("v1", "plate", "CAM-001", "2026-07-01T09:00:00", plate="abc123")
        service = DetectionReportService()

        overview = service.overview(from_date="2026-07-01", to_date="2026-07-01")
        daily = service.personnel_daily(from_date="2026-07-01", to_date="2026-07-01", gap_minutes=15)
        sessions = service.personnel_sessions(person_id="094", from_date="2026-07-01", to_date="2026-07-01", gap_minutes=15)
        monthly = service.personnel_monthly(year=2026, month=7, gap_minutes=15)
        plates = service.plates(from_date="2026-07-01", to_date="2026-07-01")
        cameras = service.cameras()

        self.assertEqual(overview["person_events"], 3)
        self.assertEqual(overview["people_detected"], 1)
        self.assertEqual(overview["plates_detected"], 1)
        self.assertEqual(daily[0]["sessions"], 2)
        self.assertEqual(daily[0]["reentries"], 1)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(monthly[0]["days_present"], 1)
        self.assertEqual(plates[0]["plate"], "ABC123")
        self.assertEqual(cameras[0]["camera_name"], "Acceso")

    def test_invalid_range_is_rejected(self):
        with self.assertRaises(ValueError):
            DetectionReportService().overview(from_date="2026-07-02", to_date="2026-07-01")

    @staticmethod
    def _event(
        uid: str,
        event_type: str,
        camera_id: str,
        detected_at: str,
        *,
        person_id: str = "",
        person_name: str = "",
        plate: str = "",
    ) -> CameraEventHistory:
        current_tz = timezone.get_current_timezone()
        parsed = timezone.make_aware(datetime.fromisoformat(detected_at), current_tz)
        return CameraEventHistory.objects.create(
            event_type=event_type,
            event_category="vehiculo" if event_type == "plate" else "reconocimiento_facial",
            origin="fixed_camera",
            camera_id=camera_id,
            camera_name="Acceso",
            detected_at=parsed,
            detected_date=parsed.date(),
            title="Evento detectado",
            person_id=person_id or None,
            person_name=person_name or None,
            plate=plate or None,
            status="new",
            severity="info",
            event_uid=uid,
            detail_payload={},
            manifest_payload={},
        )
