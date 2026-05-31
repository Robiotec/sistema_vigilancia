from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

from back.app.core.helpers import BaseHelper


class CameraNormalizer(BaseHelper):
    """Normaliza cámaras desde API Central al contrato del frontend."""

    inference_suffix_pattern = re.compile(r"\s*-\s*INF\s*$", re.IGNORECASE)

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

    def inference_enabled(self, camera: dict[str, Any], stream: dict[str, Any] | None = None) -> bool:
        name = self.text(camera.get("name"))
        path = self.text(
            stream.get("path") or stream.get("mediamtx_path") if stream else "",
            self.text(camera.get("unique_code") or camera.get("name")),
        )
        origin_url = self.text((stream or {}).get("origin_url") or camera.get("rtsp_url") or camera.get("url_stream"))
        parsed_origin_path = ""
        if origin_url:
            try:
                parsed_origin_path = self.text(urlparse(origin_url).path)
            except Exception:
                parsed_origin_path = origin_url
        return (
            bool(self.inference_suffix_pattern.search(name))
            or path.upper().rstrip("/").endswith("/INFERENCE")
            or parsed_origin_path.upper().rstrip("/").endswith("/INFERENCE")
        )

    def item(self, camera: dict[str, Any], stream: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self.text(
            stream.get("path") or stream.get("mediamtx_path") if stream else "",
            self.text(camera.get("unique_code") or camera.get("name"), "camera"),
        )
        camera_type = self.text(camera.get("camera_type") or camera.get("kind") or camera.get("type") or "fixed")
        inference_type = self.text(camera.get("inference_type") or camera.get("tipo_inferencia"), "inactiva")
        unique_code = self.text(camera.get("unique_code"), path)
        origin_url = self.text((stream or {}).get("origin_url") or camera.get("rtsp_url") or camera.get("url_stream"))
        active = self.active(camera.get("active"))
        channel = self.display_channel(camera)
        inference_enabled = self.inference_enabled(camera, stream)
        effective_path = path
        if inference_enabled and path and not path.upper().rstrip("/").endswith("/INFERENCE"):
            effective_path = f"{path.rstrip('/')}/INFERENCE"
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
            "viewer_url": f"/api/camera-viewer-url?camera={quote(effective_path)}",
            "path": effective_path,
            "organization_name": self.text(camera.get("company_id"), "ROBIOTEC"),
            "organizacion_id": self.num_id(camera.get("company_id")),
            "organizacion_source_id": self.text(camera.get("company_id")),
            "tipo_camara_codigo": camera_type,
            "tipo_camara_nombre": camera_type,
            "tipo_inferencia": inference_type,
            "inference_type": inference_type,
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
            "hacer_inferencia": inference_enabled,
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
