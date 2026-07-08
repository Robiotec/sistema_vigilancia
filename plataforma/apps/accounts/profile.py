from __future__ import annotations

from typing import Any

import bcrypt
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.utils import timezone

from apps.accounts.models import LegacyUser
from apps.accounts.roles import ROLE_LABELS, LegacyRoleService
from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.organizations.models import Company


class ProfileError(ValueError):
    pass


class ProfileService:
    def __init__(self, roles: LegacyRoleService | None = None):
        self.roles = roles or LegacyRoleService()

    def load(self, current_user) -> dict[str, object]:
        legacy_user = self._legacy_user(current_user)
        role_names = self.roles.role_names_for_user(current_user)
        return {
            "user": self._user_payload(legacy_user, role_names),
            "stats": self._stats(legacy_user, role_names),
            "updated_at": timezone.now().isoformat(),
        }

    def update(self, current_user, payload: dict[str, Any] | None) -> dict[str, object]:
        source = payload if isinstance(payload, dict) else {}
        legacy_user = self._legacy_user(current_user)
        name = _clean(source.get("name"))
        email = _clean(source.get("email"))
        if not name:
            raise ProfileError("Ingresa un nombre visible.")
        if email:
            try:
                validate_email(email)
            except Exception as exc:
                raise ProfileError("Ingresa un correo valido.") from exc
            if (
                LegacyUser.objects.exclude(id=legacy_user.id)
                .filter(email__iexact=email)
                .exists()
            ):
                raise ProfileError("Ese correo ya esta asignado a otro usuario.")

        current_password = str(source.get("current_password") or "")
        new_password = str(source.get("new_password") or "")
        confirm_password = str(source.get("confirm_password") or "")
        if new_password:
            if len(new_password) < 6:
                raise ProfileError("La nueva contrasena debe tener al menos 6 caracteres.")
            if confirm_password and confirm_password != new_password:
                raise ProfileError("La confirmacion de contrasena no coincide.")
            if not current_password or not self._verify_password(current_password, legacy_user.password_hash):
                raise ProfileError("La contrasena actual no es correcta.")
            legacy_user.password_hash = self._hash_password(new_password)

        legacy_user.name = name
        legacy_user.email = email or None
        legacy_user.updated_at = timezone.now()
        legacy_user.save(update_fields=["name", "email", "password_hash", "updated_at"])
        self._sync_django_user(current_user, legacy_user)
        return self.load(current_user)

    def _legacy_user(self, current_user) -> LegacyUser:
        legacy_user = self.roles.legacy_user_for_django_user(current_user)
        if legacy_user is None:
            raise PermissionError("Usuario no encontrado.")
        return legacy_user

    def _stats(self, legacy_user: LegacyUser, role_names: list[str]) -> dict[str, int]:
        is_master = "master" in set(role_names)
        filters = {} if is_master else {"company_id": legacy_user.company_id}
        return {
            "companies": Company.objects.filter(active=True).count() if is_master else int(bool(legacy_user.company_id)),
            "cameras": Camera.objects.filter(active=True, **filters).count(),
            "vehicles": Vehicle.objects.filter(active=True, **filters).count(),
            "rboxes": RBox.objects.filter(active=True, **filters).count(),
            "drones": Drone.objects.filter(active=True, **filters).count(),
        }

    @staticmethod
    def _user_payload(legacy_user: LegacyUser, role_names: list[str]) -> dict[str, object]:
        role_label = ", ".join(ROLE_LABELS.get(role, role) for role in role_names) or "Sin rol"
        company = legacy_user.company
        return {
            "id": str(legacy_user.id),
            "username": legacy_user.username,
            "name": legacy_user.name or legacy_user.username,
            "email": legacy_user.email or "",
            "company_id": str(legacy_user.company_id) if legacy_user.company_id else "",
            "company_name": company.name if company else "",
            "active": legacy_user.active,
            "roles": role_names,
            "role_label": role_label,
            "created_at": legacy_user.created_at.isoformat() if legacy_user.created_at else "",
            "updated_at": legacy_user.updated_at.isoformat() if legacy_user.updated_at else "",
        }

    @staticmethod
    def _sync_django_user(current_user, legacy_user: LegacyUser) -> None:
        if not getattr(current_user, "is_authenticated", False):
            return
        UserModel = get_user_model()
        UserModel.objects.filter(username__iexact=legacy_user.username).update(
            email=legacy_user.email or "",
            first_name=legacy_user.name or legacy_user.username,
            is_active=legacy_user.active,
        )

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _clean(value: object) -> str:
    return str(value or "").strip()
