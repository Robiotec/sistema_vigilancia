from __future__ import annotations

import bcrypt
from django.utils import timezone

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.accounts.profile import ProfileError, ProfileService
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.devices.models import Camera, Vehicle
from apps.organizations.models import Company


class ProfileServiceTests(LegacySchemaTestCase):
    def test_load_returns_scoped_profile_and_stats(self):
        company = Company.objects.create(name="Cliente", active=True)
        other_company = Company.objects.create(name="Otra", active=True)
        user = self._user("admin", company)
        self._role_link(user, "admin")
        Camera.objects.create(company=company, name="Camara 1", brand="dahua", active=True)
        Camera.objects.create(company=other_company, name="Camara 2", brand="dahua", active=True)
        Vehicle.objects.create(company=company, name="Unidad", vehicle_type="auto", active=True)

        payload = ProfileService().load(user)

        self.assertEqual(payload["user"]["username"], "admin")
        self.assertEqual(payload["stats"]["cameras"], 1)
        self.assertEqual(payload["stats"]["vehicles"], 1)

    def test_update_profile_and_password(self):
        company = Company.objects.create(name="Cliente", active=True)
        user = self._user("operador", company, password="oldpass")
        self._role_link(user, "viewer")

        payload = ProfileService().update(
            user,
            {
                "name": "Operador Nuevo",
                "email": "nuevo@example.com",
                "current_password": "oldpass",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )

        user.refresh_from_db()
        self.assertEqual(payload["user"]["name"], "Operador Nuevo")
        self.assertEqual(user.email, "nuevo@example.com")
        self.assertTrue(bcrypt.checkpw(b"newpass123", user.password_hash.encode("utf-8")))

    def test_password_change_requires_current_password(self):
        company = Company.objects.create(name="Cliente", active=True)
        user = self._user("operador", company, password="oldpass")
        self._role_link(user, "viewer")

        with self.assertRaises(ProfileError):
            ProfileService().update(
                user,
                {
                    "name": "Operador",
                    "email": "operador@example.com",
                    "current_password": "bad",
                    "new_password": "newpass123",
                },
            )

    @staticmethod
    def _user(username: str, company: Company, *, password: str = "secret") -> LegacyUser:
        return LegacyUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            name=username.title(),
            company=company,
            active=True,
            password_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _role_link(user: LegacyUser, role_name: str) -> None:
        role = Role.objects.create(name=role_name, active=True, created_at=timezone.now(), updated_at=timezone.now())
        UserRole.objects.create(user_id=user.id, role=role, active=True, created_at=timezone.now())
