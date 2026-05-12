from __future__ import annotations

from typing import Any
from urllib.parse import quote

from back.app.config import Settings
from back.app.core.helpers import DashboardHelper


class CameraFormMapper:
    """Construye payloads de Camara y sus variantes del UML."""

    def __init__(self, helper: DashboardHelper, settings: Settings) -> None:
        self.helper = helper
        self.settings = settings

    def generated_code(self) -> str:
        return self.helper.generated_device_id("CAM")

    def quality_from_payload(self, payload: dict[str, Any]) -> str | None:
        quality = self.helper.text(payload.get("calidad") or payload.get("quality")).lower()
        if quality in {"mainstream", "substream"}:
            return quality
        if self.helper.bool_value(payload.get("substream")):
            return "substream"
        return "mainstream" if self.helper.text(payload.get("marca")) else None

    def rtsp_preview(self, payload: dict[str, Any]) -> dict[str, str]:
        brand = self.helper.text(payload.get("marca"), "custom").lower()
        user = self.helper.text(payload.get("usuario"))
        password = self.helper.text(payload.get("password"))
        ip = self.helper.text(payload.get("ip"))
        port = int(payload.get("puerto") or 554)
        channel = int(payload.get("canal") or 1)
        auth = f"{quote(user)}:{quote(password)}@" if user or password else ""
        if brand == "hikvision":
            hikvision_channel = channel if channel >= 100 else int(f"{channel}{'02' if payload.get('substream') else '01'}")
            path = f"Streaming/Channels/{hikvision_channel}"
        elif brand == "dahua":
            path = f"cam/realmonitor?channel={channel}&subtype={1 if payload.get('substream') else 0}"
        elif brand == "axis":
            path = "axis-media/media.amp"
        else:
            path = self.helper.text(payload.get("ruta_personalizada"), "stream1").lstrip("/")
        return {"url": f"rtsp://{auth}{ip}:{port}/{path}", "brand": brand}

    def api_payload(
        self,
        payload: dict[str, Any],
        *,
        companies: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
        rboxes: list[dict[str, Any]],
        default_company_id: Any,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        company_id = (
            self.helper.resolve_source_id(companies, payload.get("organizacion_id"))
            or (existing or {}).get("company_id")
            or default_company_id
        )
        rbox_id = self.helper.resolve_source_id(rboxes, payload.get("rbox_id"))
        kind = self.helper.text(
            payload.get("tipo_camara_codigo") or payload.get("tipo_camara"),
            (existing or {}).get("camera_type") or "fixed",
        )
        linked_vehicle_id = self.helper.resolve_source_id(vehicles, payload.get("vehiculo_id"))
        linked_vehicle = next(
            (
                item
                for item in vehicles
                if self.helper.text(item.get("id")) == self.helper.text(linked_vehicle_id)
            ),
            None,
        )
        if kind == "vehicle" and linked_vehicle and linked_vehicle.get("company_id"):
            company_id = linked_vehicle.get("company_id")
        name = self.helper.text(payload.get("nombre"), (existing or {}).get("name") or "Camara")
        code = self.helper.text(payload.get("codigo_unico"), (existing or {}).get("unique_code") or self.generated_code())
        quality = self.quality_from_payload(payload)
        stream_index = 1 if quality == "substream" else 0 if quality == "mainstream" else None
        brand = self.helper.text(payload.get("marca"), (existing or {}).get("brand") or "custom")
        channel = self.helper.optional_int(payload.get("canal") or payload.get("rtsp_channel"))
        if brand.lower() == "hikvision" and channel is not None and channel < 100:
            suffix = "02" if quality == "substream" else "01"
            channel = int(f"{channel}{suffix}")
        data = {
            "company_id": company_id,
            "name": name,
            "brand": brand,
            "model": self.helper.text(payload.get("modelo")) or None,
            "rtsp_url": self.helper.text(payload.get("url_rtsp") or payload.get("rtsp_url")) or None,
            "unique_code": code,
            "camera_type": kind,
            "protocol": self.helper.text(payload.get("protocolo_codigo") or payload.get("protocolo"), "rtsp"),
            "ip": self.helper.text(payload.get("ip_camaras_fijas") or payload.get("ip") or payload.get("rtsp_host")) or None,
            "port": self.helper.optional_int(payload.get("puerto") or payload.get("rtsp_port")),
            "username": self.helper.text(payload.get("usuario_stream")) or None,
            "channel": channel,
            "stream": stream_index,
            "quality": quality,
            "public_ip_enabled": self.helper.bool_value(payload.get("tiene_ip_publica")),
            "uses_rbox": self.helper.bool_value(payload.get("usa_rbox")) or bool(rbox_id) or kind == "rbox",
            "rbox_id": rbox_id,
            "vehicle_id": linked_vehicle_id if kind == "vehicle" else None,
            "vehicle_position": self.helper.text(payload.get("vehiculo_posicion") or payload.get("vehicle_position")) or None,
            "drone_id": linked_vehicle_id if kind == "drone" else None,
            "active": payload.get("activa", True),
            "can_publish": True,
        }
        password = self.helper.text(payload.get("password_stream"))
        if password:
            data["password_encrypted"] = password
        elif existing and existing.get("password_encrypted"):
            data["password_encrypted"] = existing.get("password_encrypted")
        return data
