from __future__ import annotations

from typing import Any

from back.app.core.helpers import BaseHelper


class StreamConfigMapper(BaseHelper):
    """StreamConfig del UML."""

    def by_drone(self, stream_configs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(item.get("drone_id")): item for item in stream_configs if item.get("drone_id")}

    def by_resource(self, stream_paths: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(item.get("resource_id")): item for item in stream_paths}

    def drone_stream_path_payload(self, company_id: Any, drone_id: Any, path: str) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "path": path,
            "resource_type": "drone",
            "resource_id": drone_id,
            "active": True,
            "can_publish": True,
        }
