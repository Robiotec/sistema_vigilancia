from __future__ import annotations

import bcrypt
from django.utils import timezone

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Vehicle
from apps.geofences.models import Geofence, GeofenceAlert
from apps.geofences.services import GeofenceAdminService
from apps.organizations.models import Company


class GeofenceAdminServiceTests(LegacySchemaTestCase):
    def test_master_creates_polygon_and_reads_overview(self):
        company = self._company("Cliente")
        master = self._user("master", None)
        self._role_link(master, self._role("master"))

        created = GeofenceAdminService().create(
            master,
            {
                "company_id": str(company.id),
                "name": "Patio norte",
                "type": "polygon",
                "color": "#8b5cf6",
                "geometry": {
                    "type": "Polygon",
                    "coordinate_order": "latlon",
                    "coordinates": [[-2.1, -79.9], [-2.1, -79.8], [-2.2, -79.8]],
                },
                "active": True,
            },
        )

        overview = GeofenceAdminService().overview(master)

        self.assertEqual(created["name"], "Patio norte")
        self.assertEqual(created["color"], "#8b5cf6")
        self.assertEqual(created["company_id"], str(company.id))
        self.assertEqual(overview["summary"]["geofences"], 1)
        self.assertEqual(overview["summary"]["active"], 1)
        self.assertEqual(overview["companies"], [{"id": str(company.id), "name": "Cliente"}])

    def test_admin_is_scoped_to_own_company(self):
        own_company = self._company("Propia")
        other_company = self._company("Otra")
        admin = self._user("admin", own_company)
        self._role_link(admin, self._role("admin"))
        own = Geofence.objects.create(
            company=own_company,
            name="Zona propia",
            geofence_type="circle",
            geometry={"type": "Circle", "center": {"lat": -2.1, "lon": -79.9}, "radius_m": 100},
            active=True,
        )
        other = Geofence.objects.create(
            company=other_company,
            name="Zona ajena",
            geofence_type="circle",
            geometry={"type": "Circle", "center": {"lat": -1.1, "lon": -78.9}, "radius_m": 100},
            active=True,
        )

        overview = GeofenceAdminService().overview(admin)
        created = GeofenceAdminService().create(
            admin,
            {
                "company_id": str(other_company.id),
                "name": "Nueva local",
                "type": "circle",
                "lat": -2.12,
                "lon": -79.91,
                "radius_m": 80,
            },
        )

        self.assertEqual([item["name"] for item in overview["geofences"]], ["Zona propia"])
        self.assertEqual(created["company_id"], str(own_company.id))
        with self.assertRaises(FileNotFoundError):
            GeofenceAdminService().update(admin, str(other.id), {"name": "No", "type": "circle"})
        GeofenceAdminService().delete(admin, str(own.id))
        own.refresh_from_db()
        self.assertFalse(own.active)
        self.assertIsNotNone(own.deleted_at)

    def test_alerts_can_be_marked_processed(self):
        company = self._company("Cliente")
        admin = self._user("admin", company)
        self._role_link(admin, self._role("admin"))
        vehicle = Vehicle.objects.create(company=company, name="Unidad 1", plate="ABC123", active=True)
        geofence = Geofence.objects.create(
            company=company,
            name="Base",
            geofence_type="circle",
            geometry={"type": "Circle", "center": {"lat": -2.1, "lon": -79.9}, "radius_m": 100},
            active=True,
        )
        alert = GeofenceAlert.objects.create(
            vehicle=vehicle,
            plate="ABC123",
            geofence=geofence,
            geofence_name="Base",
            event_type="enter",
            gps_at=timezone.now(),
            recorded_at=timezone.now(),
            latitude=-2.1,
            longitude=-79.9,
            processed=False,
            payload={},
        )

        alerts = GeofenceAdminService().list_alerts(admin)
        updated = GeofenceAdminService().mark_alert_processed(admin, str(alert.id), processed=True)

        self.assertEqual(len(alerts), 1)
        self.assertFalse(alerts[0]["processed"])
        self.assertTrue(updated["processed"])
        alert.refresh_from_db()
        self.assertTrue(alert.processed)

    @staticmethod
    def _company(name: str) -> Company:
        return Company.objects.create(name=name, active=True, created_at=timezone.now(), updated_at=timezone.now())

    @staticmethod
    def _role(name: str) -> Role:
        return Role.objects.create(name=name, active=True, created_at=timezone.now(), updated_at=timezone.now())

    @staticmethod
    def _user(username: str, company: Company | None) -> LegacyUser:
        return LegacyUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            name=username.title(),
            company=company,
            active=True,
            password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8"),
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _role_link(user: LegacyUser, role: Role) -> None:
        UserRole.objects.create(user_id=user.id, role=role, active=True, created_at=timezone.now())
