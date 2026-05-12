from __future__ import annotations

from typing import Any

from back.app.domain.cameras.static_camera import StaticCameraConfig


class PtzCameraConfig(StaticCameraConfig):
    """camaraptz: camara con control arriba/abajo/izquierda/derecha."""

    camera_type = "ptz"

    def control_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "estado": payload.get("estado", True),
            "arriba": payload.get("arriba"),
            "abajo": payload.get("abajo"),
            "izquierda": payload.get("izquierda"),
            "derecha": payload.get("derecha"),
        }
