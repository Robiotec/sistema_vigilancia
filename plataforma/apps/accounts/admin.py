from django.contrib import admin

from apps.accounts.models import LegacyUser, Role, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    search_fields = ("name", "description")


@admin.register(LegacyUser)
class LegacyUserAdmin(admin.ModelAdmin):
    list_display = ("username", "name", "email", "company", "active")
    list_filter = ("active", "company")
    search_fields = ("username", "name", "email")
    readonly_fields = ("password_hash",)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("legacy_user", "role", "active")
    list_filter = ("active", "role")
    search_fields = ("role__name",)
