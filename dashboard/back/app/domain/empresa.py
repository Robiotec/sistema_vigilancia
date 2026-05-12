from __future__ import annotations

from typing import Any

from back.app.core.helpers import BaseHelper


class EmpresaMapper(BaseHelper):
    """Representa la entidad Empresa del UML para opciones del dashboard."""

    def item(self, empresa: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self.num_id(empresa.get("id")),
            "source_id": empresa.get("id"),
            "nombre": empresa.get("name") or empresa.get("nombre"),
            "ruc": empresa.get("ruc"),
            "activa": empresa.get("active", empresa.get("estado", True)),
        }


class EmpresaService:
    """Operaciones de Empresa consumidas por las rutas del dashboard."""

    def __init__(self, api_request) -> None:
        self.api_request = api_request

    def ensure_default(self, token: str) -> dict[str, Any]:
        empresas = self.list(token)
        if empresas:
            return empresas[0]
        return self.api_request(
            "/companies",
            method="POST",
            token=token,
            data={"name": "ROBIOTEC", "active": True},
        )

    def list(self, token: str) -> list[dict[str, Any]]:
        return self.api_request("/companies", token=token) or []

    def options(self, token: str) -> list[dict[str, Any]]:
        empresas = self.list(token)
        return empresas or [self.ensure_default(token)]
