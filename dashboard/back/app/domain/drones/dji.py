from __future__ import annotations

from typing import Any

from back.app.domain.drones.base import BaseDroneNormalizer


class DjiDroneNormalizer(BaseDroneNormalizer):
    """Normalizador específico para Dron DJI."""

    vehicle_type_code = "drone_dji"
    vehicle_type_name = "Dron DJI"
    manufacturer = "DJI"
    telemetry_mode = "rtmp"

    def rtmp_url(self, generated_id: str, stream_config: dict[str, Any] | None = None) -> str:
        configured_url = self.text(stream_config.get("origin_url") if stream_config else "")
        if configured_url:
            return configured_url
        return f"rtmp://{self.settings.public_host}:{self.settings.mediamtx_rtmp_port}/{generated_id}"
