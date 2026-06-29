from __future__ import annotations

import time
from typing import Any

from back.app.core.helpers import BaseHelper


_VEHICLE_TYPE_LABELS = {
    "auto": "Vehiculo terrestre",
    "automovil": "Vehiculo terrestre",
    "vehiculo": "Vehiculo terrestre",
}


_VEHICLE_SUBTYPE_LABELS = {
    "camioneta": "Camioneta",
    "camion": "Camion",
    "camión": "Camion",
    "volqueta": "Volqueta",
    "retroexcavadora": "Retroexcavadora",
    "otra": "Otra",
}


def vehicle_type_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return _VEHICLE_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title() if normalized else "Vehiculo terrestre")


def vehicle_subtype_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return _VEHICLE_SUBTYPE_LABELS.get(normalized, normalized.replace("_", " ").title() if normalized else "")


class VehicleNormalizer(BaseHelper):
    """Normaliza carros y vehículos terrestres."""

    def item(
        self,
        vehicle: dict[str, Any],
        companies: dict[str, dict[str, Any]] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        vehicle_type = self.text(vehicle.get("vehicle_type"), "auto")
        vehicle_type_name = vehicle_type_label(vehicle_type)
        vehicle_subtype = self.text(vehicle.get("vehicle_subtype"))
        vehicle_subtype_name = vehicle_subtype_label(vehicle_subtype)
        driver_name = self.text(vehicle.get("driver_name"))
        generated_id = self.text(vehicle.get("unique_code") or vehicle.get("plate"), self.text(vehicle.get("id")))
        company = (companies or {}).get(str(vehicle.get("company_id")), {})
        owner = (users or {}).get(str(vehicle.get("owner_user_id")), {})
        return {
            "registration_id": str(vehicle.get("id")),
            "id": self.num_id(vehicle.get("id")),
            "source_id": vehicle.get("id"),
            "entry_kind": "manual",
            "vehicle_type": vehicle_type,
            "vehicle_type_code": vehicle_type,
            "vehicle_type_name": vehicle_type_name,
            "vehicle_subtype": vehicle_subtype,
            "vehicle_subtype_name": vehicle_subtype_name,
            "tipo_vehiculo_codigo": vehicle_type,
            "tipo_vehiculo_nombre": vehicle_type_name,
            "tipo_automovil_codigo": vehicle_subtype,
            "tipo_automovil_nombre": vehicle_subtype_name,
            "label": self.text(vehicle.get("name"), "Vehiculo"),
            "identifier": generated_id,
            "placa": self.text(vehicle.get("plate")),
            "nombre": self.text(vehicle.get("name"), "Vehiculo"),
            "driver_name": driver_name,
            "chofer": driver_name,
            "telemetry_mode": "api",
            "api_device_id": generated_id,
            "generated_id": generated_id,
            "organizacion_id": self.num_id(vehicle.get("company_id")),
            "organizacion_source_id": self.text(vehicle.get("company_id")),
            "organizacion_nombre": self.text(company.get("name")),
            "propietario_usuario_id": self.num_id(vehicle.get("owner_user_id")),
            "propietario_source_id": self.text(vehicle.get("owner_user_id")),
            "propietario_usuario": self.text(owner.get("username")),
            "propietario_display_name": self.text(owner.get("email") or owner.get("username")),
            "notes": "",
            "cameras": [],
            "ts": time.time(),
            "active": self.active(vehicle.get("active")),
        }
