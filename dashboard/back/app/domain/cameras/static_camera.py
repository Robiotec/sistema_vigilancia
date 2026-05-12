from __future__ import annotations

from typing import Any

from back.app.core.helpers import BaseHelper


class StaticCameraConfig(BaseHelper):
    """camestatica: RTSP fijo con localidad, protocolo, puerto, canal y stream."""

    camera_type = "fixed"

    def rtsp_path(self, payload: dict[str, Any]) -> str:
        return self.text(payload.get("ruta_personalizada"), "stream1").lstrip("/")
