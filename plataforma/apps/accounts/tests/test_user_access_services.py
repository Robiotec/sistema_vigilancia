from __future__ import annotations

import bcrypt
from django.utils import timezone

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.accounts.services import AccountAdminError, UserAccessAdminService
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.organizations.models import Company


class UserAccessAdminServiceTests(LegacySchemaTestCase):
    def test_master_creates_user_with_role_and_password_hash(self):
        company = self._company("Cliente")
        master = self._user("master", None)
        self._role_link(master, self._role("master"))
        self._role("viewer")

        payload = UserAccessAdminService().create_user(
            master,
            {
                "username": "operador",
                "email": "operador@example.com",
                "name": "Operador",
                "password": "secret123",
                "company_id": str(company.id),
                "role_names": ["viewer"],
            },
        )

        created = LegacyUser.objects.get(username="operador")
        self.assertEqual(payload["role_names"], ["viewer"])
        self.assertEqual(created.company_id, company.id)
        self.assertNotEqual(created.password_hash, "secret123")
        self.assertTrue(bcrypt.checkpw(b"secret123", created.password_hash.encode("utf-8")))

    def test_admin_is_scoped_to_own_company_and_allowed_roles(self):
        own_company = self._company("Propia")
        other_company = self._company("Otra")
        admin = self._user("admin", own_company)
        self._role_link(admin, self._role("admin"))
        self._role("viewer")
        self._role("operator_cameras")
        self._role("master")
        self._user("visible", own_company)
        self._user("hidden", other_company)

        service = UserAccessAdminService()
        overview = service.overview(admin)

        self.assertEqual([item["username"] for item in overview["users"]], ["admin", "visible"])
        self.assertEqual({item["name"] for item in overview["roles"]}, {"operator_cameras", "viewer"})
        with self.assertRaises(AccountAdminError):
            service.create_user(
                admin,
                {
                    "username": "bad",
                    "password": "secret123",
                    "role_names": ["master"],
                    "company_id": str(other_company.id),
                },
            )

    def test_only_master_can_manage_companies(self):
        company = self._company("Cliente")
        admin = self._user("admin", company)
        self._role_link(admin, self._role("admin"))
        master = self._user("master", None)
        self._role_link(master, self._role("master"))
        service = UserAccessAdminService()

        with self.assertRaises(PermissionError):
            service.create_company(admin, {"name": "Bloqueada"})

        created = service.create_company(master, {"name": "Nueva", "address": "Sucursal"})

        self.assertEqual(created["name"], "Nueva")
        self.assertTrue(Company.objects.filter(name="Nueva", address="Sucursal").exists())

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
