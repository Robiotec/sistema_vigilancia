from __future__ import annotations

from django.utils import timezone

from apps.alerts.models import CameraEventHistory
from apps.alerts.services import EventHistoryService
from apps.core.tests.legacy_schema import LegacySchemaTestCase


class EventHistoryServiceTests(LegacySchemaTestCase):
    def test_list_filters_events_and_paginates(self):
        first = self._event(
            event_uid="evt-1",
            event_type="plate",
            event_category="vehiculo",
            camera_id="CAM-001",
            camera_name="Acceso principal",
            plate="ABC123",
            title="Vehiculo detectado",
        )
        self._event(
            event_uid="evt-2",
            event_type="person",
            event_category="alerta",
            camera_id="CAM-002",
            camera_name="Bodega",
            person_name="Operador",
            title="Persona detectada",
        )

        payload = EventHistoryService().list({"q": "ABC123", "event_types": "plate", "page_size": "1"})

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["total_pages"], 1)
        self.assertEqual(payload["items"][0]["id"], str(first.id))
        self.assertEqual(payload["items"][0]["primary"], "ABC123")

    def test_filter_options_returns_camera_counts(self):
        self._event(event_uid="evt-1", camera_id="CAM-001", camera_name="Acceso principal")
        self._event(event_uid="evt-2", camera_id="CAM-001", camera_name="Acceso principal")
        self._event(event_uid="evt-3", camera_id="CAM-002", camera_name="Bodega")

        payload = EventHistoryService().filter_options("camera_id")

        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["items"][0], {"value": "CAM-001", "label": "CAM-001", "count": 2})

    def test_update_status_validates_allowed_values(self):
        event = self._event(event_uid="evt-1", status="new")
        service = EventHistoryService()

        payload = service.update_status(str(event.id), "reviewed")

        event.refresh_from_db()
        self.assertEqual(payload["status"], "reviewed")
        self.assertEqual(event.status, "reviewed")
        with self.assertRaises(ValueError):
            service.update_status(str(event.id), "pendiente")

    @staticmethod
    def _event(**overrides):
        now = timezone.now()
        values = {
            "event_type": "plate",
            "event_category": "vehiculo",
            "origin": "fixed_camera",
            "camera_id": "CAM-001",
            "camera_name": "Acceso principal",
            "detected_at": now,
            "detected_date": now.date(),
            "title": "Evento detectado",
            "status": "new",
            "severity": "info",
            "event_uid": "evt",
            "detail_payload": {"confidence": 0.92},
            "manifest_payload": {},
            "created_at": now,
            "updated_at": now,
        }
        values.update(overrides)
        return CameraEventHistory.objects.create(**values)
