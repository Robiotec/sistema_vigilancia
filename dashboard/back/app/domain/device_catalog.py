from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote, urlencode

from back.app.config import Settings
from back.app.core.helpers import BaseHelper


class DeviceCatalogBuilder(BaseHelper):
    """Construye catálogos de cámara/dispositivo para el frontend."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def drone_camera_item(self, drone_item: dict[str, Any]) -> dict[str, Any]:
        path = self.text(drone_item.get("mediamtx_path") or drone_item.get("video_path") or drone_item.get("identifier"))
        name = self.text(drone_item.get("label"), "Dron")
        dom_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"drone-{path or name}").strip("-").lower()
        viewer_url = self.text(drone_item.get("video_iframe_url")) or f"{self.settings.mediamtx_webrtc_base_url.rstrip('/')}/{quote(path)}"
        return {
            "id": self.num_id(drone_item.get("source_id") or drone_item.get("registration_id")),
            "source_id": drone_item.get("source_id") or drone_item.get("registration_id"),
            "name": name,
            "display_name": f"{name} · video",
            "dom_id": dom_id,
            "url": viewer_url,
            "viewer_url": viewer_url,
            "path": path,
            "organization_name": self.text(drone_item.get("organizacion_nombre"), "ROBIOTEC"),
            "tipo_camara_codigo": "drone",
            "tipo_camara_nombre": "Camara de dron",
            "marca": "Robiotec" if drone_item.get("vehicle_type_code") == "drone_robiotec" else "DJI",
            "modelo": self.text(drone_item.get("vehicle_type_name")),
            "rbox_id": "",
            "vehiculo_id": "",
            "vehiculo_source_id": self.text(drone_item.get("source_id") or drone_item.get("registration_id")),
            "drone_id": self.text(drone_item.get("source_id") or drone_item.get("registration_id")),
            "drone_source_id": self.text(drone_item.get("source_id") or drone_item.get("registration_id")),
            "activa": self.active(drone_item.get("active")),
            "hacer_inferencia": False,
            "stream_url": viewer_url,
            "url_stream": viewer_url,
            "url_rtsp": "",
            "codigo_unico": path,
            "usa_rbox": False,
            "tiene_ip_publica": True,
            "auto_generated": True,
        }

    def device_from_camera(self, item: dict[str, Any]) -> dict[str, Any]:
        source = self.text(item.get("url") or item.get("stream_url") or item.get("viewer_url"))
        return {
            "camera_name": item["name"],
            "display_name": item["display_name"],
            "camera_id": item.get("id"),
            "camera_type": item["tipo_camara_codigo"],
            "kind": item["tipo_camara_codigo"],
            "source": source,
            "viewer_url": item.get("viewer_url") or item.get("url") or "",
            "organization_name": item.get("organization_name") or "",
            "capabilities": {"audio": True, "telemetry": item["tipo_camara_codigo"] in {"vehicle", "drone"}},
        }

    def device_from_vehicle(self, item: dict[str, Any], camera: dict[str, Any] | None = None) -> dict[str, Any]:
        is_drone = self.text(item.get("vehicle_type_code") or item.get("vehicle_type")).startswith("drone")
        camera_name = self.text((camera or {}).get("name")) or (self.text(item.get("label")) if is_drone else "")
        viewer_url = self.text((camera or {}).get("viewer_url") or item.get("video_iframe_url"))
        return {
            "device_id": self.text(item.get("api_device_id") or item.get("identifier") or item.get("registration_id")),
            "camera_id": self.num_id((camera or {}).get("id")),
            "camera_name": camera_name,
            "display_name": self.text(item.get("label") or item.get("identifier")),
            "device_kind": "vehicle",
            "vehicle_source_id": self.text(item.get("source_id") or item.get("registration_id")),
            "vehicle_type": "dron" if is_drone else "automovil",
            "vehicle_type_code": self.text(item.get("vehicle_type_code") or item.get("vehicle_type")),
            "api_device_id": self.text(item.get("api_device_id")),
            "mediamtx_path": self.text((camera or {}).get("path") or item.get("mediamtx_path") or item.get("video_path")),
            "source": viewer_url,
            "viewer_url": viewer_url,
            "organization_name": self.text(item.get("organizacion_nombre")),
            "capabilities": {"audio": bool(camera) or is_drone, "telemetry": item.get("telemetry_mode") == "api"},
        }

    def camera_switcher_fallback(self, camera_items: list[dict[str, Any]]) -> str:
        if not camera_items:
            return '<div class="empty-state">No hay cámaras registradas.</div>'
        rows = []
        for item in camera_items:
            name = self.text(item.get("name"))
            if not name:
                continue
            label = re.sub(r"\s*[·-]\s*video\s*$", "", self.text(item.get("display_name") or name), flags=re.I).upper()
            camera_type = self.text(item.get("tipo_camara_nombre") or item.get("tipo_camara_codigo") or "Camara")
            preview_query = urlencode({"camera_name": name})
            viewer_url = f"/api/camera-preview-frame?{preview_query}"
            preview = (
                '<span class="camera-pill-preview">'
                f'<iframe class="camera-pill-frame" src="{escape(viewer_url)}" title="Vista previa {escape(label)}" loading="lazy" allow="autoplay; fullscreen; picture-in-picture"></iframe>'
                '</span>'
            )
            rows.append(
                '<article class="camera-pill-shell">'
                f'<a class="camera-pill" href="/camaras?camera={quote(name)}" data-camera-name="{escape(name)}">'
                f'{preview}'
                '<span class="camera-pill-main">'
                '<span class="camera-pill-topline">'
                '<span class="camera-pill-led tone-idle"></span>'
                f'<span class="camera-pill-title">{escape(label)}</span>'
                '</span>'
                f'<span class="camera-pill-association">{escape("Asociada a " + name if item.get("tipo_camara_codigo") in {"drone", "vehicle"} else camera_type)}</span>'
                '<span class="camera-pill-status">Lista</span>'
                '</span>'
                f'<span class="camera-pill-tags"><span class="camera-pill-tag">{escape(camera_type)}</span></span>'
                '</a>'
                '</article>'
            )
        return "".join(rows) or '<div class="empty-state">No hay cámaras registradas.</div>'
