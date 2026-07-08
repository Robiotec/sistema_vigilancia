from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import bcrypt
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.accounts.roles import ADMIN_ASSIGNABLE_ROLE_NAMES, ROLE_LABELS, SUPPORTED_ROLE_NAMES, LegacyRoleService
from apps.organizations.models import Company


class AccountAdminError(ValueError):
    pass


@dataclass(frozen=True)
class AccessContext:
    legacy_user: LegacyUser
    role_names: set[str]

    @property
    def is_master(self) -> bool:
        return "master" in self.role_names

    @property
    def is_admin(self) -> bool:
        return bool({"master", "admin"}.intersection(self.role_names))


class UserAccessAdminService:
    def __init__(self, role_service: LegacyRoleService | None = None):
        self.role_service = role_service or LegacyRoleService()

    def overview(self, current_user) -> dict[str, object]:
        context = self._context(current_user)
        users = self.list_users(current_user, context=context)
        companies = self.list_companies(current_user, context=context)
        roles = self.list_roles(current_user, context=context)
        return {
            "users": users,
            "companies": companies,
            "roles": roles,
            "summary": {
                "users": len(users),
                "companies": len(companies),
                "roles": len(roles),
                "scope": "global" if context.is_master else "organizacion",
                "updated_at": timezone.now().isoformat(),
            },
        }

    def list_users(self, current_user, *, context: AccessContext | None = None) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        queryset = LegacyUser.objects.select_related("company").order_by("username")
        if not context.is_master:
            queryset = queryset.filter(company_id=context.legacy_user.company_id)
        users = list(queryset)
        roles_by_user = self._roles_by_user([user.id for user in users])
        return [self._user_item(user, roles_by_user.get(user.id, [])) for user in users]

    def list_roles(self, current_user, *, context: AccessContext | None = None) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        allowed = set(SUPPORTED_ROLE_NAMES) if context.is_master else ADMIN_ASSIGNABLE_ROLE_NAMES
        user_ids = list(LegacyUser.objects.values_list("id", flat=True))
        if not context.is_master:
            user_ids = list(
                LegacyUser.objects.filter(company_id=context.legacy_user.company_id).values_list("id", flat=True)
            )
        assigned_counts = dict(
            UserRole.objects.filter(active=True, role__name__in=allowed, user_id__in=user_ids)
            .values("role_id")
            .annotate(total=Count("user_id"))
            .values_list("role_id", "total")
        )
        roles = Role.objects.filter(active=True, name__in=allowed).order_by("name")
        return [
            {
                "id": str(role.id),
                "name": role.name,
                "label": ROLE_LABELS.get(role.name, role.name),
                "description": role.description or "",
                "active": role.active,
                "users": int(assigned_counts.get(role.id, 0)),
            }
            for role in roles
        ]

    def list_companies(self, current_user, *, context: AccessContext | None = None) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        queryset = Company.objects.order_by("name")
        if not context.is_master:
            queryset = queryset.filter(id=context.legacy_user.company_id)
        return [self._company_item(company) for company in queryset]

    @transaction.atomic
    def create_user(self, current_user, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user)
        data = self._clean_user_payload(payload, creating=True)
        role_names = self._normalize_role_names(data.pop("role_names", None))
        company = self._company_for_user(data.pop("company_id", None), role_names, context)
        self._validate_unique_user(data["username"], data.get("email"))

        user = LegacyUser.objects.create(
            username=data["username"],
            email=data.get("email") or None,
            name=data.get("name") or data["username"],
            company=company,
            active=data["active"],
            password_hash=self._hash_password(data["password"]),
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self._replace_roles(user, role_names)
        return self._user_item(user, role_names)

    @transaction.atomic
    def update_user(self, current_user, user_id: str, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user)
        user = self._scoped_user(context, user_id)
        data = self._clean_user_payload(payload, creating=False)
        role_names = self._normalize_role_names(data.pop("role_names", None)) if "role_names" in data else None
        if role_names is not None:
            user.company = self._company_for_user(data.pop("company_id", user.company_id), role_names, context)
        elif not context.is_master:
            user.company_id = context.legacy_user.company_id
        elif "company_id" in data:
            user.company = self._optional_company(data.pop("company_id"))

        username = data.get("username")
        email = data.get("email")
        self._validate_unique_user(username, email, exclude_user=user)
        for field in ("username", "email", "name", "active"):
            if field in data:
                setattr(user, field, data[field] or None if field == "email" else data[field])
        if data.get("password"):
            user.password_hash = self._hash_password(data["password"])
        user.updated_at = timezone.now()
        user.save()
        if role_names is not None:
            self._replace_roles(user, role_names)
        return self._user_item(user, role_names or self._roles_by_user([user.id]).get(user.id, []))

    @transaction.atomic
    def delete_user(self, current_user, user_id: str) -> None:
        context = self._context(current_user)
        user = self._scoped_user(context, user_id)
        if user.id == context.legacy_user.id:
            raise AccountAdminError("No puedes eliminar tu propio usuario desde esta pantalla.")
        user.active = False
        user.deleted_at = timezone.now()
        user.updated_at = timezone.now()
        user.save(update_fields=["active", "deleted_at", "updated_at"])
        UserRole.objects.filter(user_id=user.id).update(active=False)

    @transaction.atomic
    def create_company(self, current_user, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user)
        self._require_master(context)
        data = self._clean_company_payload(payload)
        self._validate_unique_company(data["name"])
        company = Company.objects.create(
            name=data["name"],
            ruc=data.get("ruc") or None,
            address=data.get("address") or None,
            active=data["active"],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return self._company_item(company)

    @transaction.atomic
    def update_company(self, current_user, company_id: str, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user)
        self._require_master(context)
        company = Company.objects.filter(id=company_id).first()
        if company is None:
            raise FileNotFoundError("Organizacion no encontrada")
        data = self._clean_company_payload(payload)
        self._validate_unique_company(data["name"], exclude_company=company)
        company.name = data["name"]
        company.ruc = data.get("ruc") or None
        company.address = data.get("address") or None
        company.active = data["active"]
        company.updated_at = timezone.now()
        company.save()
        return self._company_item(company)

    @transaction.atomic
    def delete_company(self, current_user, company_id: str) -> None:
        context = self._context(current_user)
        self._require_master(context)
        company = Company.objects.filter(id=company_id).first()
        if company is None:
            raise FileNotFoundError("Organizacion no encontrada")
        if LegacyUser.objects.filter(company=company).exists():
            raise AccountAdminError("No puedes eliminar una organizacion con usuarios activos.")
        company.active = False
        company.deleted_at = timezone.now()
        company.updated_at = timezone.now()
        company.save(update_fields=["active", "deleted_at", "updated_at"])

    def _context(self, current_user) -> AccessContext:
        legacy_user = self.role_service.legacy_user_for_django_user(current_user)
        if legacy_user is None:
            raise PermissionError("Usuario no encontrado")
        role_names = set(self.role_service.role_names_for_user(current_user))
        if not {"master", "admin"}.intersection(role_names):
            raise PermissionError("No autorizado")
        return AccessContext(legacy_user=legacy_user, role_names=role_names)

    def _scoped_user(self, context: AccessContext, user_id: str) -> LegacyUser:
        queryset = LegacyUser.objects.all()
        if not context.is_master:
            queryset = queryset.filter(company_id=context.legacy_user.company_id)
        user = queryset.filter(id=user_id).first()
        if user is None:
            raise FileNotFoundError("Usuario no encontrado")
        return user

    def _company_for_user(self, company_id: object, role_names: list[str], context: AccessContext) -> Company | None:
        self._validate_assignable_roles(role_names, context)
        if "master" in role_names:
            return None
        if not context.is_master:
            if not context.legacy_user.company_id:
                raise AccountAdminError("Administrador sin organizacion asignada.")
            return context.legacy_user.company
        company = self._optional_company(company_id)
        if company is None:
            raise AccountAdminError("Todo usuario no master debe estar asignado a una organizacion.")
        return company

    @staticmethod
    def _optional_company(company_id: object) -> Company | None:
        value = _clean(company_id)
        if not value:
            return None
        company = Company.objects.filter(id=value).first()
        if company is None:
            raise AccountAdminError("Organizacion no valida.")
        return company

    @staticmethod
    def _replace_roles(user: LegacyUser, role_names: list[str]) -> None:
        roles = list(Role.objects.filter(active=True, name__in=role_names))
        if len(roles) != len(set(role_names)):
            raise AccountAdminError("Rol invalido.")
        UserRole.objects.filter(user_id=user.id).delete()
        now = timezone.now()
        for role in roles:
            UserRole.objects.create(user_id=user.id, role=role, active=True, created_at=now)

    @staticmethod
    def _roles_by_user(user_ids) -> dict[object, list[str]]:
        result: dict[object, list[str]] = {user_id: [] for user_id in user_ids}
        rows = (
            UserRole.objects.select_related("role")
            .filter(user_id__in=user_ids, active=True, role__active=True)
            .values_list("user_id", "role__name")
        )
        for user_id, role_name in rows:
            if role_name in SUPPORTED_ROLE_NAMES:
                result.setdefault(user_id, []).append(role_name)
        return result

    @staticmethod
    def _clean_user_payload(payload: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        data: dict[str, Any] = {}
        if creating or "username" in source:
            data["username"] = _clean(source.get("username"))
            if not data["username"]:
                raise AccountAdminError("Ingresa un usuario.")
            if len(data["username"]) > 80:
                raise AccountAdminError("El usuario no puede superar 80 caracteres.")
        if "email" in source:
            email = _clean(source.get("email"))
            if email:
                try:
                    validate_email(email)
                except Exception as exc:
                    raise AccountAdminError("Ingresa un correo valido.") from exc
            data["email"] = email
        elif creating:
            data["email"] = ""
        if creating or "name" in source:
            data["name"] = _clean(source.get("name")) or data.get("username", "")
        if creating or "active" in source:
            data["active"] = _bool(source.get("active"), True)
        if creating or "company_id" in source:
            data["company_id"] = _clean(source.get("company_id"))
        if creating or "role_names" in source:
            data["role_names"] = source.get("role_names")
        password = str(source.get("password") or "")
        if creating and len(password) < 6:
            raise AccountAdminError("La contrasena debe tener al menos 6 caracteres.")
        if password:
            data["password"] = password
        return data

    @staticmethod
    def _clean_company_payload(payload: dict[str, Any]) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        name = _clean(source.get("name") or source.get("nombre"))
        if not name:
            raise AccountAdminError("Ingresa el nombre de la organizacion.")
        return {
            "name": name,
            "ruc": _clean(source.get("ruc")),
            "address": _clean(source.get("address") or source.get("description") or source.get("descripcion")),
            "active": _bool(source.get("active", source.get("activa")), True),
        }

    @staticmethod
    def _normalize_role_names(raw: object) -> list[str]:
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = raw
        else:
            values = ["viewer"]
        normalized = []
        for item in values:
            value = _clean(item)
            if value and value not in normalized:
                normalized.append(value)
        return normalized or ["viewer"]

    @staticmethod
    def _validate_assignable_roles(role_names: list[str], context: AccessContext) -> None:
        unsupported = set(role_names) - set(SUPPORTED_ROLE_NAMES)
        if unsupported:
            raise AccountAdminError("Rol invalido.")
        if context.is_master:
            if "master" in role_names and len(role_names) > 1:
                raise AccountAdminError("El rol master no debe combinarse con otros roles.")
            return
        forbidden = set(role_names) - ADMIN_ASSIGNABLE_ROLE_NAMES
        if forbidden:
            raise AccountAdminError("Un administrador solo puede crear operadores o visores.")

    @staticmethod
    def _validate_unique_user(username: str | None, email: str | None, *, exclude_user: LegacyUser | None = None) -> None:
        queryset = LegacyUser.objects.all()
        if exclude_user is not None:
            queryset = queryset.exclude(id=exclude_user.id)
        if username and queryset.filter(username__iexact=username).exists():
            raise AccountAdminError("Ya existe un usuario con ese nombre.")
        if email and queryset.filter(email__iexact=email).exists():
            raise AccountAdminError("Ya existe un usuario con ese correo.")

    @staticmethod
    def _validate_unique_company(name: str, *, exclude_company: Company | None = None) -> None:
        queryset = Company.objects.all()
        if exclude_company is not None:
            queryset = queryset.exclude(id=exclude_company.id)
        if queryset.filter(name__iexact=name).exists():
            raise AccountAdminError("Ya existe una organizacion con ese nombre.")

    @staticmethod
    def _require_master(context: AccessContext) -> None:
        if not context.is_master:
            raise PermissionError("Solo master puede administrar organizaciones.")

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _user_item(user: LegacyUser, role_names: list[str]) -> dict[str, object]:
        return {
            "id": str(user.id),
            "username": user.username,
            "name": user.name or "",
            "email": user.email or "",
            "active": user.active,
            "company_id": str(user.company_id) if user.company_id else "",
            "company_name": user.company.name if user.company_id and user.company else "",
            "role_names": role_names,
            "role_label": ", ".join(ROLE_LABELS.get(role, role) for role in role_names) or "Sin rol",
        }

    @staticmethod
    def _company_item(company: Company) -> dict[str, object]:
        return {
            "id": str(company.id),
            "name": company.name,
            "ruc": company.ruc or "",
            "address": company.address or "",
            "active": company.active,
        }


def _clean(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}
