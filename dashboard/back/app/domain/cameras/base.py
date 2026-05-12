from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from back.app.core.helpers import BaseHelper


class CameraNormalizer(BaseHelper):
    """Normaliza cámaras desde API Central al contrato del frontend."""

    def display_channel(self, camera: dict[str, Any]) -> int | None:
        channel = self.optional_int(camera.get("channel"))
        if channel is None:
            return None
        brand = self.text(camera.get("brand")).lower()
        quality = self.text(camera.get("quality"), "mainstream").lower()
        stream = self.optional_int(camera.get("stream"))
        if brand == "hikvision" and channel < 100:
            suffix = "02" if quality == "substream" or stream == 1 else "01"
            return int(f"{channel}{suffix}")
        return channel

    def item(self, camera: dict[str, Any], stream: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self.text(
            stream.get("path") or stream.get("mediamtx_path") if stream else "",
            self.text(camera.get("unique_code") or camera.get("name"), "camera"),
        )
        camera_type = self.text(camera.get("camera_type") or camera.get("kind") or camera.get("type") or "fixed")
        unique_code = self.text(camera.get("unique_code"), path)
        origin_url = self.text((stream or {}).get("origin_url") or camera.get("rtsp_url") or camera.get("url_stream"))
        active = self.active(camera.get("active"))
        channel = self.display_channel(camera)
        return {
            "id": self.num_id(camera.get("id")),
            "source_id": camera.get("id"),
            "nombre": self.text(camera.get("name"), "Camara"),
            "name": self.text(camera.get("name"), "Camara"),
            "codigo": unique_code,
            "activo": active,
            "display_name": self.text(camera.get("name"), "Camara"),
            "dom_id": re.sub(r"[^a-zA-Z0-9_-]+", "-", self.text(camera.get("name"), "camera")).strip("-").lower(),
            "url": self.text((stream or {}).get("viewer_url") or (stream or {}).get("output_webrtc_url") or camera.get("url")),
            "viewer_url": f"/api/camera-viewer-url?camera={quote(path)}",
            "path": path,
            "organization_name": self.text(camera.get("company_id"), "ROBIOTEC"),
            "organizacion_id": self.num_id(camera.get("company_id")),
            "organizacion_source_id": self.text(camera.get("company_id")),
            "tipo_camara_codigo": camera_type,
            "tipo_camara_nombre": camera_type,
            "marca": self.text(camera.get("brand"), "generic"),
            "modelo": self.text(camera.get("model")),
            "rbox_id": self.num_id(camera.get("rbox_id")),
            "rbox_source_id": self.text(camera.get("rbox_id")),
            "vehiculo_id": self.num_id(camera.get("vehicle_id") or camera.get("drone_id")),
            "vehiculo_source_id": self.text(camera.get("vehicle_id") or camera.get("drone_id")),
            "vehiculo_posicion": self.text(camera.get("vehicle_position")),
            "drone_id": self.num_id(camera.get("drone_id")),
            "drone_source_id": self.text(camera.get("drone_id")),
            "activa": active,
            "hacer_inferencia": False,
            "stream_url": origin_url,
            "url_stream": origin_url,
            "url_rtsp": origin_url,
            "codigo_unico": unique_code,
            "ip_camaras_fijas": self.text(camera.get("ip")),
            "ip_camara": self.text(camera.get("ip")),
            "puerto": camera.get("port"),
            "canal": channel,
            "channel": channel,
            "stream": camera.get("stream"),
            "calidad": self.text(camera.get("quality")),
            "usuario_stream": self.text(camera.get("username")),
            "usa_rbox": bool(camera.get("uses_rbox")),
            "tiene_ip_publica": bool(camera.get("public_ip_enabled")),
        }
