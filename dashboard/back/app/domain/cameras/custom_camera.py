from __future__ import annotations

from typing import Any

from back.app.domain.cameras.static_camera import StaticCameraConfig


class CustomCameraConfig(StaticCameraConfig):
    """CamaraPerso: camara con URL RTMP personalizada."""

    camera_type = "custom"

    def rtmp_url(self, payload: dict[str, Any]) -> str:
        return self.text(payload.get("url_rtmp") or payload.get("rtmp_url"))
