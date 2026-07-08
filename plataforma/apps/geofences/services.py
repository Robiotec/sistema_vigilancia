from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LegacyUser
from apps.accounts.roles import LegacyRoleService
from apps.geofences.models import Geofence, GeofenceAlert
from apps.organizations.models import Company


class GeofenceAdminError(ValueError):
    pass


@dataclass(frozen=True)
class GeofenceStay:
    geofence_name: str
    entered_at: object | None
    exited_at: object | None
    minutes_inside: float


class GeofenceReportService:
    def vehicle_events(self, vehicle_id: str, start, end) -> list[GeofenceAlert]:
        return list(
            GeofenceAlert.objects.filter(
                vehicle_id=vehicle_id,
                recorded_at__gte=start,
                recorded_at__lt=end,
            ).order_by("recorded_at")
        )


@dataclass(frozen=True)
class GeofenceContext:
    legacy_user: LegacyUser
    role_names: set[str]

    @property
    def is_master(self) -> bool:
        return "master" in self.role_names


class GeofenceAdminService:
    supported_types = {"circle", "polygon"}

    def __init__(self, role_service: LegacyRoleService | None = None):
        self.role_service = role_service or LegacyRoleService()

    def overview(self, current_user) -> dict[str, object]:
        context = self._context(current_user)
        geofences = self.list_geofences(current_user, context=context)
        alerts = self.list_alerts(current_user, context=context, limit=80)
        companies = self.list_companies(current_user, context=context)
        active = sum(1 for item in geofences if item["active"])
        pending_alerts = sum(1 for item in alerts if not item["processed"])
        return {
            "geofences": geofences,
            "alerts": alerts,
            "companies": companies,
            "summary": {
                "geofences": len(geofences),
                "active": active,
                "inactive": len(geofences) - active,
                "pending_alerts": pending_alerts,
                "scope": "global" if context.is_master else "organizacion",
                "updated_at": timezone.now().isoformat(),
            },
        }

    def list_geofences(
        self,
        current_user,
        *,
        context: GeofenceContext | None = None,
    ) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        queryset = Geofence.objects.select_related("company").order_by("name")
        if not context.is_master:
            queryset = queryset.filter(company_id=context.legacy_user.company_id)
        return [self.geofence_item(geofence) for geofence in queryset]

    def list_companies(
        self,
        current_user,
        *,
        context: GeofenceContext | None = None,
    ) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        queryset = Company.objects.filter(active=True).order_by("name")
        if not context.is_master:
            queryset = queryset.filter(id=context.legacy_user.company_id)
        return [{"id": str(company.id), "name": company.name} for company in queryset]

    def list_alerts(
        self,
        current_user,
        *,
        context: GeofenceContext | None = None,
        limit: int = 100,
        processed: bool | None = None,
    ) -> list[dict[str, object]]:
        context = context or self._context(current_user)
        limit = min(max(int(limit or 100), 1), 500)
        queryset = GeofenceAlert.objects.select_related("vehicle", "geofence").order_by("-recorded_at")
        if processed is not None:
            queryset = queryset.filter(processed=processed)
        if not context.is_master:
            queryset = queryset.filter(geofence__company_id=context.legacy_user.company_id)
        return [self.alert_item(alert) for alert in queryset[:limit]]

    @transaction.atomic
    def create(self, current_user, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user, write=True)
        data = self._clean_payload(payload)
        company = self._resolve_company(data.pop("company_id", ""), context)
        geofence = Geofence.objects.create(company=company, **data)
        return self.geofence_item(geofence)

    @transaction.atomic
    def update(self, current_user, geofence_id: str, payload: dict[str, Any]) -> dict[str, object]:
        context = self._context(current_user, write=True)
        geofence = self._scoped_geofence(geofence_id, context)
        data = self._clean_payload(payload, existing=geofence)
        company_id = data.pop("company_id", "")
        if company_id:
            geofence.company = self._resolve_company(company_id, context)
        for field, value in data.items():
            setattr(geofence, field, value)
        geofence.updated_at = timezone.now()
        geofence.save()
        return self.geofence_item(geofence)

    @transaction.atomic
    def delete(self, current_user, geofence_id: str) -> None:
        context = self._context(current_user, write=True)
        geofence = self._scoped_geofence(geofence_id, context)
        geofence.active = False
        geofence.deleted_at = timezone.now()
        geofence.updated_at = timezone.now()
        geofence.save(update_fields=["active", "deleted_at", "updated_at"])

    @transaction.atomic
    def mark_alert_processed(self, current_user, alert_id: str, processed: bool = True) -> dict[str, object]:
        context = self._context(current_user, write=True)
        queryset = GeofenceAlert.objects.select_related("vehicle", "geofence")
        if not context.is_master:
            queryset = queryset.filter(geofence__company_id=context.legacy_user.company_id)
        alert = queryset.filter(id=alert_id).first()
        if alert is None:
            raise FileNotFoundError("Alerta no encontrada")
        alert.processed = processed
        alert.save(update_fields=["processed"])
        return self.alert_item(alert)

    def _context(self, current_user, *, write: bool = False) -> GeofenceContext:
        legacy_user = self.role_service.legacy_user_for_django_user(current_user)
        if legacy_user is None:
            raise PermissionError("Usuario no encontrado")
        role_names = set(self.role_service.role_names_for_user(current_user))
        if write and not self.role_service.can_edit_devices(current_user):
            raise PermissionError("No autorizado")
        if not write and not self.role_service.can_view_devices(current_user):
            raise PermissionError("No autorizado")
        return GeofenceContext(legacy_user=legacy_user, role_names=role_names)

    def _scoped_geofence(self, geofence_id: str, context: GeofenceContext) -> Geofence:
        queryset = Geofence.objects.select_related("company")
        if not context.is_master:
            queryset = queryset.filter(company_id=context.legacy_user.company_id)
        geofence = queryset.filter(id=geofence_id).first()
        if geofence is None:
            raise FileNotFoundError("Geocerca no encontrada")
        return geofence

    def _resolve_company(self, raw_company_id: object, context: GeofenceContext) -> Company:
        if not context.is_master:
            if not context.legacy_user.company_id:
                raise GeofenceAdminError("Usuario sin organizacion asignada.")
            return context.legacy_user.company

        company_id = _clean(raw_company_id)
        if company_id:
            company = Company.objects.filter(id=company_id, active=True).first()
            if company is None:
                raise GeofenceAdminError("Organizacion no valida.")
            return company

        if context.legacy_user.company_id:
            return context.legacy_user.company

        companies = list(Company.objects.filter(active=True).order_by("name")[:2])
        if len(companies) == 1:
            return companies[0]
        raise GeofenceAdminError("Organizacion requerida.")

    def _clean_payload(self, payload: dict[str, Any], *, existing: Geofence | None = None) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        name = _clean(source.get("name") or source.get("nombre") or (existing.name if existing else ""))
        if not name:
            raise GeofenceAdminError("Nombre requerido.")

        geofence_type = _clean(
            source.get("type") or source.get("geofence_type") or (existing.geofence_type if existing else "")
        ).lower()
        if geofence_type not in self.supported_types:
            raise GeofenceAdminError("Tipo de geocerca invalido.")

        if existing and not self._has_geometry_payload(source):
            geometry = self._apply_style(source, _json_object(existing.geometry))
        else:
            geometry = self._normalize_geometry(source, geofence_type)

        description = source.get("description", source.get("descripcion", existing.description if existing else ""))
        return {
            "company_id": _clean(
                source.get("company_id")
                or source.get("company")
                or source.get("organization_id")
                or source.get("organizacion_id")
            ),
            "name": name,
            "geofence_type": geofence_type,
            "geometry": geometry,
            "active": _bool(source.get("active"), existing.active if existing else True),
            "description": _clean(description) or None,
        }

    @staticmethod
    def _has_geometry_payload(source: dict[str, Any]) -> bool:
        return any(
            key in source
            for key in (
                "geometry",
                "coordinates",
                "lat",
                "latitude",
                "lon",
                "lng",
                "longitude",
                "radius_m",
                "radius",
            )
        )

    def _normalize_geometry(self, payload: dict[str, Any], geofence_type: str) -> dict[str, Any]:
        geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
        if geofence_type == "circle":
            center = geometry.get("center") if isinstance(geometry.get("center"), dict) else {}
            lat = _to_float(_first_present(payload.get("lat"), payload.get("latitude"), center.get("lat"), geometry.get("lat")))
            lon = _to_float(
                _first_present(
                    payload.get("lon"),
                    payload.get("lng"),
                    payload.get("longitude"),
                    center.get("lon"),
                    center.get("lng"),
                    geometry.get("lon"),
                    geometry.get("lng"),
                )
            )
            radius_m = _to_float(
                _first_present(payload.get("radius_m"), payload.get("radius"), geometry.get("radius_m"), geometry.get("radius"))
            )
            if lat is None or lon is None or radius_m is None or radius_m <= 0:
                raise GeofenceAdminError("Geocerca circular invalida.")
            return self._apply_style(
                payload,
                {"type": "Circle", "center": {"lat": lat, "lon": lon}, "radius_m": radius_m},
            )

        coordinates = geometry.get("coordinates") or payload.get("coordinates") or []
        points = self._normalize_polygon_points(coordinates, geometry)
        if len(points) < 3:
            raise GeofenceAdminError("Geocerca poligonal invalida.")
        return self._apply_style(
            payload,
            {"type": "Polygon", "coordinate_order": "latlon", "coordinates": points},
        )

    @staticmethod
    def _normalize_polygon_points(coordinates: object, geometry: dict[str, Any]) -> list[list[float]]:
        raw_points = coordinates
        coordinate_order = _clean(geometry.get("coordinate_order")).lower()
        is_geojson_polygon = _clean(geometry.get("type")).lower() == "polygon" and coordinate_order != "latlon"
        if is_geojson_polygon and isinstance(raw_points, list) and raw_points and isinstance(raw_points[0], list):
            if raw_points[0] and isinstance(raw_points[0][0], list):
                raw_points = raw_points[0]
            if not coordinate_order:
                coordinate_order = "lonlat"

        points: list[list[float]] = []
        if not isinstance(raw_points, list):
            return points
        for point in raw_points:
            lat = lon = None
            if isinstance(point, dict):
                lat = _to_float(point.get("lat"))
                lon = _to_float(_first_present(point.get("lon"), point.get("lng")))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                first = _to_float(point[0])
                second = _to_float(point[1])
                if first is not None and second is not None:
                    if coordinate_order and coordinate_order != "latlon":
                        lat, lon = second, first
                    else:
                        lat, lon = first, second
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                points.append([lat, lon])
        return points

    def _apply_style(self, payload: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(geometry)
        existing_style = normalized.get("style") if isinstance(normalized.get("style"), dict) else {}
        payload_style = payload.get("style") if isinstance(payload.get("style"), dict) else {}
        payload_geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
        payload_geometry_style = payload_geometry.get("style") if isinstance(payload_geometry.get("style"), dict) else {}
        color = _normalize_color(
            payload.get("color"),
            payload.get("fillColor"),
            payload.get("fill_color"),
            payload_style.get("color"),
            payload_style.get("fillColor"),
            payload_geometry.get("color"),
            payload_geometry_style.get("color"),
            payload_geometry_style.get("fillColor"),
            normalized.get("color"),
            existing_style.get("color"),
            existing_style.get("fillColor"),
        )
        if color:
            normalized["color"] = color
            normalized["style"] = {**existing_style, "color": color, "fillColor": color}
        return normalized

    @staticmethod
    def geofence_item(geofence: Geofence) -> dict[str, object]:
        geometry = _json_object(geofence.geometry)
        style = geometry.get("style") if isinstance(geometry.get("style"), dict) else {}
        color = _normalize_color(geometry.get("color"), style.get("color"), style.get("fillColor"))
        return {
            "id": str(geofence.id),
            "company_id": str(geofence.company_id),
            "company_name": geofence.company.name if geofence.company_id and geofence.company else "",
            "name": geofence.name,
            "type": geofence.geofence_type,
            "geofence_type": geofence.geofence_type,
            "geometry": geometry,
            "coordinates": geometry.get("coordinates"),
            "style": style,
            "color": color,
            "active": geofence.active,
            "description": geofence.description or "",
            "created_at": geofence.created_at.isoformat() if geofence.created_at else None,
            "updated_at": geofence.updated_at.isoformat() if geofence.updated_at else None,
        }

    @staticmethod
    def alert_item(alert: GeofenceAlert) -> dict[str, object]:
        return {
            "id": str(alert.id),
            "vehicle_id": str(alert.vehicle_id),
            "vehicle_name": alert.vehicle.name if alert.vehicle_id and alert.vehicle else "",
            "plate": alert.plate or "",
            "geofence_id": str(alert.geofence_id),
            "geofence_name": alert.geofence_name,
            "event_type": alert.event_type,
            "gps_at": alert.gps_at.isoformat() if alert.gps_at else None,
            "recorded_at": alert.recorded_at.isoformat() if alert.recorded_at else None,
            "lat": alert.latitude,
            "lon": alert.longitude,
            "processed": alert.processed,
            "payload": _json_object(alert.payload),
        }


def _clean(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "falso", "no", "off", "inactivo"}


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalize_color(*values: object) -> str | None:
    for value in values:
        raw = _clean(value).lower()
        if not raw:
            continue
        if not raw.startswith("#"):
            raw = f"#{raw}"
        hex_value = raw[1:]
        if len(hex_value) in {3, 6} and all(char in "0123456789abcdef" for char in hex_value):
            return raw
    return None
