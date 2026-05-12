from __future__ import annotations

import time
from typing import Any

from back.app.config import Settings
from back.app.domain.vehicles.base import VehicleNormalizer


class BaseDroneNormalizer(VehicleNormalizer):
    """Clase padre para drones."""

    vehicle_type_code = "drone_robiotec"
    vehicle_type_name = "Dron Robiotec"
    manufacturer = "Robiotec"
    telemetry_mode = "api"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def rtmp_url(self, generated_id: str, stream_config: dict[str, Any] | None = None) -> str:
        return self.text(stream_config.get("origin_url") if stream_config else "")

    def item(
        self,
        drone: dict[str, Any],
        stream_config: dict[str, Any] | None = None,
        companies: dict[str, dict[str, Any]] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        generated_id = self.text(drone.get("unique_code"), self.text(drone.get("id")))
        mediamtx_path = generated_id
        company = (companies or {}).get(str(drone.get("company_id")), {})
        owner = (users or {}).get(str(drone.get("owner_user_id")), {})
        viewer_url = f"{self.settings.mediamtx_webrtc_base_url.rstrip('/')}/{mediamtx_path or generated_id}"
        return {
            "registration_id": str(drone.get("id")),
            "id": self.num_id(drone.get("id")),
            "source_id": drone.get("id"),
            "entry_kind": "manual",
            "vehicle_type": self.vehicle_type_code,
            "vehicle_type_code": self.vehicle_type_code,
            "vehicle_type_name": self.vehicle_type_name,
            "tipo_vehiculo_codigo": self.vehicle_type_code,
            "tipo_vehiculo_nombre": self.vehicle_type_name,
            "label": self.text(drone.get("name"), "Dron"),
            "identifier": generated_id,
            "nombre": self.text(drone.get("name"), "Dron"),
            "telemetry_mode": self.telemetry_mode,
            "api_device_id": generated_id if self.telemetry_mode == "api" else "",
            "generated_id": generated_id,
            "mediamtx_path": mediamtx_path,
            "video_path": mediamtx_path,
            "rtmp_url": self.rtmp_url(generated_id, stream_config),
            "video_iframe_url": viewer_url,
            "organizacion_id": self.num_id(drone.get("company_id")),
            "organizacion_source_id": self.text(drone.get("company_id")),
            "organizacion_nombre": self.text(company.get("name")),
            "propietario_usuario_id": self.num_id(drone.get("owner_user_id")),
            "propietario_source_id": self.text(drone.get("owner_user_id")),
            "propietario_usuario": self.text(owner.get("username")),
            "propietario_display_name": self.text(owner.get("email") or owner.get("username")),
            "notes": "",
            "cameras": [],
            "ts": time.time(),
            "active": self.active(drone.get("active")),
        }
