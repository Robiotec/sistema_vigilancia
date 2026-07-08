from __future__ import annotations

import bcrypt
from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.accounts.roles import LegacyRoleService
from apps.core.permissions import DeviceRolePermission
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.devices.services import CameraAdminService, DeviceAdminError, DroneAdminService, RBoxAdminService, VehicleAdminService
from apps.organizations.models import Company
from apps.streaming.models import StreamConfig, StreamPath


class DeviceAdminServiceTests(LegacySchemaTestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa Test", active=True)
        self.master_role = Role.objects.create(name="master", active=True)
        self.viewer_role = Role.objects.create(name="viewer", active=True)
        self.master_user = self._legacy_user("master", "secret", self.master_role)
        self.viewer_user = self._legacy_user("viewer", "secret", self.viewer_role)

    def test_authenticates_legacy_user_and_reads_roles(self):
        user = authenticate(username="master", password="secret")

        self.assertIsNotNone(user)
        self.assertEqual(user.username, "master")
        self.assertEqual(LegacyRoleService().role_names_for_user(user), ["master"])

    def test_device_permissions_follow_legacy_roles(self):
        master = authenticate(username="master", password="secret")
        viewer = authenticate(username="viewer", password="secret")
        permission = DeviceRolePermission()

        self.assertTrue(permission.has_permission(_request("GET", master), None))
        self.assertTrue(permission.has_permission(_request("POST", master), None))
        self.assertTrue(permission.has_permission(_request("GET", viewer), None))
        self.assertFalse(permission.has_permission(_request("POST", viewer), None))
        self.assertFalse(permission.has_permission(_request("GET", AnonymousUser()), None))

    def test_rbox_service_generates_serial(self):
        rbox = RBoxAdminService().create({"company": self.company, "name": "RBox Test"})

        self.assertTrue(rbox.serial.startswith("RBOX-"))
        self.assertTrue(RBox.objects.filter(id=rbox.id).exists())

    def test_vehicle_service_normalizes_plate_and_generates_code(self):
        vehicle = VehicleAdminService().create(
            {
                "company": self.company,
                "name": "Unidad 01",
                "plate": " abc 123 ",
                "brand": "Suzuki",
                "year": 2024,
                "vehicle_subtype": "camioneta",
                "driver_name": "Chofer Test",
            }
        )

        self.assertEqual(vehicle.plate, "ABC0123")
        self.assertEqual(vehicle.unique_code, "ABC0123")
        self.assertEqual(vehicle.brand, "Suzuki")
        self.assertEqual(vehicle.year, 2024)
        self.assertEqual(vehicle.vehicle_type, "auto")
        self.assertTrue(Vehicle.objects.filter(id=vehicle.id).exists())

    def test_vehicle_service_blocks_duplicate_plate_in_same_company(self):
        VehicleAdminService().create({"company": self.company, "name": "Unidad 01", "plate": "ABC0147"})

        with self.assertRaises(DeviceAdminError):
            VehicleAdminService().create({"company": self.company, "name": "Unidad 02", "plate": " abc147 "})

    def test_vehicle_service_keeps_four_digit_plate(self):
        vehicle = VehicleAdminService().create({"company": self.company, "name": "Unidad 01", "plate": "ABC9140"})

        self.assertEqual(vehicle.plate, "ABC9140")

    def test_vehicle_service_rejects_invalid_plate(self):
        with self.assertRaises(DeviceAdminError):
            VehicleAdminService().create({"company": self.company, "name": "Unidad 01", "plate": "AB9140"})

    def test_vehicle_update_preserves_unique_code(self):
        vehicle = VehicleAdminService().create(
            {"company": self.company, "name": "Unidad 01", "plate": "ABC0123", "unique_code": "GPS-001"}
        )

        updated = VehicleAdminService().update(
            vehicle,
            {
                "company": self.company,
                "name": "Unidad Editada",
                "plate": "DEF456",
                "unique_code": "GPS-NO-DEBE-CAMBIAR",
            },
        )

        self.assertEqual(updated.unique_code, "GPS-001")
        self.assertEqual(updated.plate, "DEF0456")
        self.assertEqual(updated.name, "Unidad Editada")

    def test_vehicle_delete_is_soft_delete(self):
        vehicle = VehicleAdminService().create({"company": self.company, "name": "Unidad 01", "plate": "ABC0123"})

        VehicleAdminService().delete(vehicle)

        vehicle.refresh_from_db()
        self.assertFalse(vehicle.active)
        self.assertIsNotNone(vehicle.deleted_at)

    def test_camera_service_creates_stream_records(self):
        rbox = RBoxAdminService().create({"company": self.company, "name": "RBox Test"})

        camera = CameraAdminService().create(
            {
                "company": self.company,
                "rbox": rbox,
                "name": "Camara Test",
                "brand": "dahua",
                "ip": "192.168.1.50",
                "port": 554,
                "channel": 1,
                "quality": "substream",
                "camera_type": "fixed",
                "active": True,
                "can_publish": True,
            },
            raw_password="rtsp-secret",
        )

        self.assertTrue(camera.unique_code.startswith("CAM-"))
        self.assertTrue(camera.uses_rbox)
        self.assertIn("/cam/realmonitor?channel=1&subtype=1", camera.rtsp_url)
        self.assertTrue(camera.password_encrypted.startswith("fernet:"))
        self.assertTrue(StreamPath.objects.filter(resource_id=camera.id, active=True).exists())
        self.assertTrue(StreamConfig.objects.filter(camera_id=camera.id, active=True).exists())

    def test_camera_update_preserves_unique_code(self):
        camera = CameraAdminService().create(
            {
                "company": self.company,
                "name": "Camara Test",
                "brand": "custom",
                "rtsp_url": "rtsp://example.local/stream",
                "camera_type": "fixed",
                "active": True,
                "can_publish": True,
            }
        )
        original_code = camera.unique_code

        updated = CameraAdminService().update(
            camera,
            {
                "company": self.company,
                "name": "Camara Editada",
                "unique_code": "CAM-NO-DEBE-CAMBIAR",
                "brand": "custom",
                "rtsp_url": "rtsp://example.local/edited",
                "camera_type": "fixed",
                "active": True,
                "can_publish": True,
            },
        )

        self.assertEqual(updated.unique_code, original_code)
        self.assertEqual(updated.name, "Camara Editada")

    def test_camera_delete_disables_streams(self):
        camera = CameraAdminService().create(
            {
                "company": self.company,
                "name": "Camara Test",
                "brand": "custom",
                "rtsp_url": "rtsp://example.local/stream",
                "camera_type": "fixed",
                "active": True,
                "can_publish": True,
            }
        )

        CameraAdminService().delete(camera)

        camera.refresh_from_db()
        self.assertFalse(camera.active)
        self.assertFalse(StreamPath.objects.get(resource_id=camera.id).active)
        self.assertFalse(StreamConfig.all_objects.get(camera_id=camera.id).active)

    def test_drone_service_generates_code_and_stream_records(self):
        drone = DroneAdminService().create(
            {
                "company": self.company,
                "name": "Dron Test",
                "provider": "dji",
                "model": "Mavic",
                "active": True,
                "can_publish": True,
            }
        )

        self.assertTrue(drone.unique_code.startswith("DJI-"))
        self.assertEqual(drone.drone_type, "dji")
        self.assertEqual(drone.manufacturer, "DJI")
        self.assertTrue(StreamPath.objects.filter(resource_type="drone", resource_id=drone.id, active=True).exists())
        self.assertTrue(StreamConfig.objects.filter(drone_id=drone.id, active=True, input_protocol="rtmp").exists())

    def test_drone_service_blocks_duplicate_code_in_same_company(self):
        DroneAdminService().create({"company": self.company, "name": "Dron 1", "unique_code": "DRN-001"})

        with self.assertRaises(DeviceAdminError):
            DroneAdminService().create({"company": self.company, "name": "Dron 2", "unique_code": "DRN-001"})

    def test_drone_update_preserves_unique_code(self):
        drone = DroneAdminService().create({"company": self.company, "name": "Dron 1", "unique_code": "DRN-001"})

        updated = DroneAdminService().update(
            drone,
            {
                "company": self.company,
                "name": "Dron Editado",
                "unique_code": "DRN-NO-DEBE-CAMBIAR",
                "provider": "robiotec",
            },
        )

        self.assertEqual(updated.unique_code, "DRN-001")
        self.assertEqual(updated.name, "Dron Editado")

    def test_drone_delete_is_soft_delete_and_disables_streams(self):
        drone = DroneAdminService().create({"company": self.company, "name": "Dron 1", "unique_code": "DRN-001"})

        DroneAdminService().delete(drone)

        drone.refresh_from_db()
        self.assertFalse(drone.active)
        self.assertIsNotNone(drone.deleted_at)
        self.assertFalse(StreamPath.objects.get(resource_type="drone", resource_id=drone.id).active)
        self.assertFalse(StreamConfig.all_objects.get(drone_id=drone.id).active)

    def _legacy_user(self, username: str, password: str, role: Role) -> LegacyUser:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = LegacyUser.objects.create(
            company=self.company,
            username=username,
            name=username.title(),
            password_hash=password_hash,
            active=True,
        )
        UserRole.objects.create(user_id=user.id, role=role, active=True)
        return user


class _request:
    def __init__(self, method: str, user):
        self.method = method
        self.user = user
