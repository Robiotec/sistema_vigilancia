from __future__ import annotations

from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import LegacyUser, UserRole

ROLE_PERMISSIONS = {
    "master": {"admin:global", "admin:orgs", "admin:users", "edit:all", "view:all"},
    "admin": {"admin:users", "edit:org", "view:all"},
    "viewer": {"view:dashboard", "view:cameras", "view:map", "view:events", "view:vehicles", "view:reports"},
    "operator_cameras": {"view:cameras"},
    "operator_map": {"view:map", "view:vehicles"},
}

ROLE_LABELS = {
    "master": "Master ROBIOTEC",
    "admin": "Administrador de organizacion",
    "operator_cameras": "Operador solo camaras",
    "operator_map": "Operador solo mapa de carros",
    "viewer": "Visor sin edicion",
}
SUPPORTED_ROLE_NAMES = tuple(ROLE_LABELS)
ADMIN_ASSIGNABLE_ROLE_NAMES = {"operator_cameras", "operator_map", "viewer"}

LEGACY_PAGE_PERMISSIONS = {
    "master": {
        "admin_users",
        "admin_orgs",
        "edit",
        "dashboard",
        "cameras",
        "map",
        "events",
        "vehicles",
        "reports",
        "notifications",
    },
    "admin": {
        "admin_users",
        "edit",
        "dashboard",
        "cameras",
        "map",
        "events",
        "vehicles",
        "reports",
        "notifications",
    },
    "viewer": {"dashboard", "cameras", "map", "events", "vehicles", "reports"},
    "operator_cameras": {"cameras"},
    "operator_map": {"map", "vehicles"},
}


class LegacyRoleService:
    def legacy_user_for_django_user(self, user) -> LegacyUser | None:
        if isinstance(user, LegacyUser):
            return user
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return None
        return (
            LegacyUser.all_objects.filter(active=True, deleted_at__isnull=True)
            .filter(username__iexact=user.username)
            .first()
        )

    def role_names_for_user(self, user) -> list[str]:
        legacy_user = self.legacy_user_for_django_user(user)
        if legacy_user is None:
            return []
        return sorted(
            {
                link.role.name
                for link in UserRole.objects.select_related("role").filter(
                    user_id=legacy_user.id,
                    active=True,
                    role__active=True,
                    role__deleted_at__isnull=True,
                )
            }
        )

    def permissions_for_user(self, user) -> list[str]:
        permissions = {"profile:read", "profile:write"}
        for role_name in self.role_names_for_user(user):
            permissions.update(ROLE_PERMISSIONS.get(role_name, set()))
        if "view:all" in permissions:
            permissions.update(
                {
                    "view:dashboard",
                    "view:cameras",
                    "view:map",
                    "view:events",
                    "view:vehicles",
                    "view:reports",
                }
            )
        if "edit:all" in permissions:
            permissions.update({"admin:orgs", "admin:users", "edit:org"})
        return sorted(permissions)

    def page_permissions_for_user(self, user) -> set[str]:
        permissions = {"profile"}
        for role_name in self.role_names_for_user(user):
            permissions.update(LEGACY_PAGE_PERMISSIONS.get(role_name, set()))
        return permissions

    def can_access_page(self, user, permission: str) -> bool:
        return permission in self.page_permissions_for_user(user)

    def default_path_for_user(self, user) -> str:
        permissions = self.page_permissions_for_user(user)
        for permission, path in (
            ("dashboard", "/"),
            ("cameras", "/camaras/"),
            ("map", "/mapa/"),
            ("events", "/eventos/"),
            ("vehicles", "/gestion-kilometros/"),
            ("reports", "/reportes/"),
            ("profile", "/perfil/"),
        ):
            if permission in permissions:
                return path
        return "/perfil/"

    def can_view_devices(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"view:all", "view:cameras", "view:vehicles"}))

    def can_edit_devices(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"edit:all", "edit:org", "admin:global"}))

    def can_view_reports(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"view:all", "view:reports"}))

    def can_edit_reports(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"edit:all", "edit:org", "admin:global"}))

    def can_view_alerts(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"view:all", "view:events", "view:cameras"}))

    def can_edit_alerts(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"edit:all", "edit:org", "admin:global"}))

    def can_view_access_admin(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"admin:users", "admin:global"}))

    def can_edit_access_admin(self, user) -> bool:
        permissions = set(self.permissions_for_user(user))
        return bool(permissions.intersection({"admin:users", "admin:global"}))

    def is_master(self, user) -> bool:
        return "master" in set(self.role_names_for_user(user))

    def is_admin(self, user) -> bool:
        return bool({"master", "admin"}.intersection(self.role_names_for_user(user)))
