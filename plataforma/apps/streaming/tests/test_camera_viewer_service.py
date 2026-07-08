from __future__ import annotations

from django.test import override_settings
from django.utils import timezone

import bcrypt
from apps.accounts.models import LegacyUser, Role, UserRole
from apps.alerts.models import CameraEventHistory
from apps.core.services import ServiceResult
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Camera
from apps.organizations.models import Company
from apps.streaming.models import StreamConfig
from apps.streaming.services import CameraViewerService, MediaMTXPath


class FakeMediaMTXClient:
    def __init__(self, paths):
        self.paths = paths

    def list_paths(self):
        return ServiceResult.success(self.paths)


class CameraViewerServiceTests(LegacySchemaTestCase):
    @override_settings(MEDIAMTX_WEBRTC_BASE_URL="/mediamtx", ROBIOTEC_PUBLIC_HOST="robio-ai.com")
    def test_catalog_returns_viewer_url_status_and_recent_events(self):
        company = Company.objects.create(name="Robiotec", active=True)
        camera = Camera.objects.create(
            company=company,
            name="Acceso",
            brand="dahua",
            unique_code="CAM-001",
            camera_type="fixed",
            inference_type="placa",
            status="activo",
            active=True,
            can_publish=True,
        )
        StreamConfig.objects.create(
            camera=camera,
            mediamtx_path="CAM-001",
            input_protocol="rtsp",
            stream_status="activo",
            active=True,
            webrtc_enabled=True,
        )
        CameraEventHistory.objects.create(
            event_type="plate",
            event_category="vehiculo",
            origin="fixed_camera",
            camera_id="CAM-001",
            camera_name="Acceso",
            detected_at=timezone.now(),
            detected_date=timezone.localdate(),
            title="Vehiculo detectado",
            plate="ABC123",
            status="new",
            severity="info",
            event_uid="evt-1",
            detail_payload={},
            manifest_payload={},
        )

        service = CameraViewerService(FakeMediaMTXClient([MediaMTXPath(name="CAM-001", ready=True, source="publisher")]))
        payload = service.catalog()

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["path"], "CAM-001")
        self.assertEqual(item["normal_path"], "CAM-001")
        self.assertEqual(item["inference_path"], "CAM-001/INFERENCE")
        self.assertTrue(item["online"])
        self.assertTrue(item["normal_online"])
        self.assertFalse(item["inference_online"])
        self.assertEqual(item["viewer_url"], "https://robio-ai.com/mediamtx/CAM-001/")
        self.assertEqual(item["whep_url"], "https://robio-ai.com/mediamtx/CAM-001/whep")
        self.assertEqual(item["normal_viewer_url"], "https://robio-ai.com/mediamtx/CAM-001/")
        self.assertEqual(item["inference_viewer_url"], "https://robio-ai.com/mediamtx/CAM-001/INFERENCE/")
        self.assertEqual(item["events"][0]["primary"], "ABC123")
        self.assertEqual(payload["mediamtx"]["online_paths"], 1)

    @override_settings(MEDIAMTX_WEBRTC_BASE_URL="/mediamtx", ROBIOTEC_PUBLIC_HOST="robio-ai.com")
    def test_catalog_splits_inference_path_into_normal_and_inference_views(self):
        company = Company.objects.create(name="Robiotec", active=True)
        camera = self._camera(company, "Laboratorio", "CAM-INF")
        StreamConfig.objects.create(
            camera=camera,
            mediamtx_path="CAM-INF/INFERENCE",
            input_protocol="rtsp",
            stream_status="activo",
            active=True,
            webrtc_enabled=True,
        )

        service = CameraViewerService(FakeMediaMTXClient([
            MediaMTXPath(name="CAM-INF", ready=True, source="publisher"),
            MediaMTXPath(name="CAM-INF/INFERENCE", ready=True, source="publisher"),
        ]))
        payload = service.catalog()
        item = payload["items"][0]

        self.assertEqual(item["path"], "CAM-INF/INFERENCE")
        self.assertEqual(item["normal_path"], "CAM-INF")
        self.assertEqual(item["inference_path"], "CAM-INF/INFERENCE")
        self.assertTrue(item["normal_online"])
        self.assertTrue(item["inference_online"])
        self.assertEqual(item["normal_whep_url"], "https://robio-ai.com/mediamtx/CAM-INF/whep")
        self.assertEqual(item["inference_whep_url"], "https://robio-ai.com/mediamtx/CAM-INF/INFERENCE/whep")

    def test_camera_events_requires_existing_camera(self):
        service = CameraViewerService(FakeMediaMTXClient([]))

        with self.assertRaises(FileNotFoundError):
            service.camera_events("00000000-0000-0000-0000-000000000000")

    def test_set_inference_type_updates_only_supported_values(self):
        company = Company.objects.create(name="Robiotec", active=True)
        camera = self._camera(company, "Acceso", "CAM-INF")

        payload = CameraViewerService(FakeMediaMTXClient([])).set_inference_type(str(camera.id), "placa")

        camera.refresh_from_db()
        self.assertEqual(payload["inference_type"], "placa")
        self.assertEqual(camera.inference_type, "placa")

    def test_set_inference_type_rejects_unknown_values(self):
        company = Company.objects.create(name="Robiotec", active=True)
        camera = self._camera(company, "Acceso", "CAM-INF")

        with self.assertRaises(ValueError):
            CameraViewerService(FakeMediaMTXClient([])).set_inference_type(str(camera.id), "otra")

    def test_catalog_is_scoped_for_organization_admin(self):
        own_company = Company.objects.create(name="Propia", active=True)
        other_company = Company.objects.create(name="Otra", active=True)
        own_camera = self._camera(own_company, "Propia", "CAM-OWN")
        self._camera(other_company, "Otra", "CAM-OTHER")
        admin = LegacyUser.objects.create(
            username="admin",
            email="admin@example.com",
            name="Admin",
            company=own_company,
            active=True,
            password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8"),
        )
        role = Role.objects.create(name="admin", active=True)
        UserRole.objects.create(user_id=admin.id, role=role, active=True, created_at=timezone.now())

        payload = CameraViewerService(FakeMediaMTXClient([])).catalog(admin)

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["id"], str(own_camera.id))

    @staticmethod
    def _camera(company: Company, name: str, code: str) -> Camera:
        return Camera.objects.create(
            company=company,
            name=name,
            brand="dahua",
            unique_code=code,
            camera_type="fixed",
            inference_type="inactiva",
            status="activo",
            active=True,
            can_publish=True,
        )
