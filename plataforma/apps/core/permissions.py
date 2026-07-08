from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.roles import LegacyRoleService


class DeviceRolePermission(BasePermission):
    """Guard device APIs using the roles from the existing users table."""

    def has_permission(self, request, view) -> bool:
        roles = LegacyRoleService()
        user = getattr(request, "user", None)
        if request.method in SAFE_METHODS:
            return roles.can_view_devices(user)
        return roles.can_edit_devices(user)


ReadOnlyOrStaff = DeviceRolePermission


class ReportRolePermission(BasePermission):
    """Guard report APIs using the roles from the existing users table."""

    def has_permission(self, request, view) -> bool:
        roles = LegacyRoleService()
        user = getattr(request, "user", None)
        if request.method in SAFE_METHODS:
            return roles.can_view_reports(user)
        return roles.can_edit_reports(user)


class ReportAdminPermission(BasePermission):
    """Allow only admin/master-style roles to change scheduled report delivery."""

    def has_permission(self, request, view) -> bool:
        return LegacyRoleService().can_edit_reports(getattr(request, "user", None))


class AlertRolePermission(BasePermission):
    """Guard notification and alert APIs using the existing legacy roles."""

    def has_permission(self, request, view) -> bool:
        roles = LegacyRoleService()
        user = getattr(request, "user", None)
        if request.method in SAFE_METHODS:
            return roles.can_view_alerts(user)
        return roles.can_edit_alerts(user)


class AccountAdminPermission(BasePermission):
    """Guard users, roles and organization admin with legacy roles."""

    def has_permission(self, request, view) -> bool:
        roles = LegacyRoleService()
        user = getattr(request, "user", None)
        if request.method in SAFE_METHODS:
            return roles.can_view_access_admin(user)
        return roles.can_edit_access_admin(user)
