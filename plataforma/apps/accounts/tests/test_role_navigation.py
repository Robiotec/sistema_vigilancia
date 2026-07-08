from __future__ import annotations

import bcrypt
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.accounts.roles import LegacyRoleService
from apps.core.tests.legacy_schema import LegacySchemaTestCase
from apps.organizations.models import Company


class RoleNavigationTests(LegacySchemaTestCase):
    def test_page_permissions_follow_legacy_roles(self):
        company = Company.objects.create(name="Cliente", active=True)
        viewer = self._legacy_user("viewer", company)
        self._role_link(viewer, "viewer")
        camera_operator = self._legacy_user("camop", company)
        self._role_link(camera_operator, "operator_cameras")
        admin = self._legacy_user("admin", company)
        self._role_link(admin, "admin")

        roles = LegacyRoleService()

        self.assertTrue(roles.can_access_page(viewer, "cameras"))
        self.assertTrue(roles.can_access_page(viewer, "reports"))
        self.assertFalse(roles.can_access_page(viewer, "notifications"))
        self.assertFalse(roles.can_access_page(viewer, "admin_users"))
        self.assertEqual(roles.default_path_for_user(camera_operator), "/camaras/")
        self.assertTrue(roles.can_access_page(admin, "notifications"))
        self.assertTrue(roles.can_access_page(admin, "admin_users"))

    def test_html_pages_redirect_to_first_allowed_route(self):
        company = Company.objects.create(name="Cliente", active=True)
        legacy_user = self._legacy_user("mapop", company)
        self._role_link(legacy_user, "operator_map")
        django_user = get_user_model().objects.create_user(username="mapop", password="unused")
        self.client.force_login(django_user)

        response = self.client.get("/camaras/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/mapa/")

    def test_sidebar_links_are_filtered_by_role(self):
        company = Company.objects.create(name="Cliente", active=True)
        legacy_user = self._legacy_user("camop", company)
        self._role_link(legacy_user, "operator_cameras")
        django_user = get_user_model().objects.create_user(username="camop", password="unused")
        self.client.force_login(django_user)

        response = self.client.get("/camaras/")
        links = response.context["sidebar_links"]
        hrefs = {link["href"] for link in links}

        self.assertEqual(response.status_code, 200)
        self.assertIn("/camaras/", hrefs)
        self.assertIn("/perfil/", hrefs)
        self.assertNotIn("/mapa/", hrefs)
        self.assertNotIn("/notificaciones/", hrefs)
        self.assertNotIn("/usuarios/", hrefs)

    @staticmethod
    def _legacy_user(username: str, company: Company | None) -> LegacyUser:
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
    def _role_link(user: LegacyUser, role_name: str) -> None:
        role = Role.objects.create(name=role_name, active=True, created_at=timezone.now(), updated_at=timezone.now())
        UserRole.objects.create(user_id=user.id, role=role, active=True, created_at=timezone.now())
