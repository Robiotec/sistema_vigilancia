from __future__ import annotations

import bcrypt
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from apps.accounts.models import LegacyUser
from apps.accounts.roles import LegacyRoleService


class LegacyUserBackend(BaseBackend):
    """Authenticate Django sessions with the existing Robiotec users table."""

    def authenticate(self, request, username: str | None = None, password: str | None = None, **kwargs):
        identity = username or kwargs.get("username")
        if not identity or not password:
            return None

        legacy_user = (
            LegacyUser.all_objects.filter(active=True, deleted_at__isnull=True)
            .filter(username__iexact=identity)
            .first()
        )
        if legacy_user is None:
            legacy_user = (
                LegacyUser.all_objects.filter(active=True, deleted_at__isnull=True)
                .filter(email__iexact=identity)
                .first()
            )
        if legacy_user is None or not self._verify(password, legacy_user.password_hash):
            return None

        return self._sync_django_user(legacy_user)

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None

    def _sync_django_user(self, legacy_user: LegacyUser):
        role_names = set(LegacyRoleService().role_names_for_user(legacy_user))
        is_admin = bool(role_names.intersection({"master", "admin"}))
        is_master = "master" in role_names

        UserModel = get_user_model()
        django_user, _ = UserModel.objects.get_or_create(
            username=legacy_user.username,
            defaults={
                "email": legacy_user.email or "",
                "first_name": legacy_user.name or legacy_user.username,
                "is_active": legacy_user.active,
                "is_staff": is_admin,
                "is_superuser": is_master,
            },
        )

        changed = False
        field_values = {
            "email": legacy_user.email or "",
            "first_name": legacy_user.name or legacy_user.username,
            "is_active": legacy_user.active,
            "is_staff": is_admin,
            "is_superuser": is_master,
        }
        for field, value in field_values.items():
            if getattr(django_user, field) != value:
                setattr(django_user, field, value)
                changed = True

        if django_user.has_usable_password():
            django_user.set_unusable_password()
            changed = True
        if changed:
            django_user.save(update_fields=[*field_values.keys(), "password"])

        return django_user

    @staticmethod
    def _verify(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False
