from __future__ import annotations

from typing import Any
from uuid import uuid4

from back.app.core.helpers import BaseHelper


class RBoxMapper(BaseHelper):
    """Representa RBox y su asociación opcional con Camara."""

    def generated_code(self) -> str:
        return f"RBOX-{uuid4().hex[:10]}".upper()

    def item(self, rbox: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self.num_id(rbox.get("id")),
            "source_id": rbox.get("id"),
            "nombre": rbox.get("name"),
            "codigo_unico": rbox.get("serial") or rbox.get("codigo_unico"),
            "ip_local": rbox.get("local_ip") or rbox.get("ip_local"),
            "ip_publica": rbox.get("public_ip") or rbox.get("ip_publica"),
            "ip_servidor": rbox.get("server_ip"),
            "puerto_servidor": rbox.get("server_port"),
        }

    def create_payload(self, payload: dict[str, Any], company_id: Any) -> dict[str, Any]:
        serial = self.text(
            payload.get("codigo_unico")
            or payload.get("serial")
            or payload.get("rbox_codigo_unico")
            or self.generated_code()
        )
        server_port = payload.get("puerto_servidor") or payload.get("server_port")
        return {
            "company_id": company_id,
            "name": self.text(payload.get("nombre"), "RBox"),
            "serial": serial,
            "local_ip": self.text(payload.get("ip_server") or payload.get("local_ip")) or None,
            "public_ip": self.text(payload.get("public_ip")) or None,
            "server_ip": self.text(payload.get("ip_servidor") or payload.get("server_ip")) or None,
            "server_port": int(server_port) if server_port else None,
            "active": payload.get("activa", True),
        }

    def update_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "nombre" in payload or "name" in payload:
            data["name"] = self.text(payload.get("nombre") or payload.get("name"), "RBox")
        if "codigo_unico" in payload or "serial" in payload or "rbox_codigo_unico" in payload:
            data["serial"] = self.text(
                payload.get("codigo_unico")
                or payload.get("serial")
                or payload.get("rbox_codigo_unico")
            )
        if "ip_server" in payload or "local_ip" in payload:
            data["local_ip"] = self.text(payload.get("ip_server") or payload.get("local_ip")) or None
        if "public_ip" in payload:
            data["public_ip"] = self.text(payload.get("public_ip")) or None
        if "ip_servidor" in payload or "server_ip" in payload:
            data["server_ip"] = self.text(payload.get("ip_servidor") or payload.get("server_ip")) or None
        if "puerto_servidor" in payload or "server_port" in payload:
            server_port = payload.get("puerto_servidor") or payload.get("server_port")
            data["server_port"] = int(server_port) if server_port else None
        if "activa" in payload or "active" in payload:
            data["active"] = payload.get("activa", payload.get("active", True))
        return data
