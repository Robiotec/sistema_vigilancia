from __future__ import annotations

from typing import Any

from back.app.core.helpers import BaseHelper


class DroneTelemetryMapper(BaseHelper):
    """TelemetriaDron del UML."""

    def item(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": telemetry.get("id"),
            "dron_id": telemetry.get("drone_id") or telemetry.get("dron_id"),
            "latitud": telemetry.get("latitude") or telemetry.get("latitud"),
            "longitud": telemetry.get("longitude") or telemetry.get("longitud"),
            "altitud": telemetry.get("altitude") or telemetry.get("altitud"),
            "velocidad": telemetry.get("speed") or telemetry.get("velocidad"),
            "bateria": telemetry.get("battery") or telemetry.get("bateria"),
            "rumbo": telemetry.get("heading") or telemetry.get("rumbo"),
            "estado": telemetry.get("state") or telemetry.get("estado"),
            "timestamp": telemetry.get("timestamp"),
        }
