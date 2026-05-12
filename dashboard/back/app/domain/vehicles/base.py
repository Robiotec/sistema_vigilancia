from __future__ import annotations

import time
from typing import Any

from back.app.core.helpers import BaseHelper


class VehicleNormalizer(BaseHelper):
    """Normaliza carros y vehículos terrestres."""

    def item(
        self,
        vehicle: dict[str, Any],
        companies: dict[str, dict[str, Any]] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        vehicle_type = self.text(vehicle.get("vehicle_type"), "auto")
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
            "vehicle_type_name": "Vehiculo terrestre",
            "tipo_vehiculo_codigo": vehicle_type,
            "tipo_vehiculo_nombre": "Vehiculo terrestre",
            "label": self.text(vehicle.get("name"), "Vehiculo"),
            "identifier": generated_id,
            "placa": self.text(vehicle.get("plate")),
            "nombre": self.text(vehicle.get("name"), "Vehiculo"),
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
