from __future__ import annotations

from typing import Any

from back.app.domain.cameras.static_camera import StaticCameraConfig


class CarCameraConfig(StaticCameraConfig):
    """camcar: camara montada en vehiculo."""

    camera_type = "vehicle"

    def vehicle_link(self, payload: dict[str, Any]) -> Any:
        return payload.get("vehiculo_id") or payload.get("vehicle_id")
