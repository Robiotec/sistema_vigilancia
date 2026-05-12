from __future__ import annotations

from typing import Any

from back.app.core.helpers import BaseHelper


class VehicleTelemetryMapper(BaseHelper):
    """TelemetriaVehiculo del UML."""

    def inventory_item(self, device: dict[str, Any]) -> dict[str, Any] | None:
        if self.text(device.get("device_kind")).lower() != "vehicle":
            return None
        device_id = self.text(device.get("device_id") or device.get("api_device_id"))
        if not device_id:
            return None
        return {
            "device_id": device_id,
            "camera_id": self.num_id(device.get("camera_id")),
            "camera_name": self.text(device.get("camera_name")),
            "display_name": self.text(device.get("display_name") or device.get("camera_name") or device_id),
            "device_kind": "vehicle",
            "vehicle_type": self.text(device.get("vehicle_type")),
            "vehicle_type_code": self.text(device.get("vehicle_type_code")),
            "freshness": "unavailable",
            "has_live_telemetry": False,
            "mediamtx_path": self.text(device.get("mediamtx_path")),
            "viewer_url": self.text(device.get("viewer_url") or device.get("source")),
            "extra": {
                "api_device_id": self.text(device.get("api_device_id") or device_id),
                "mediamtx_path": self.text(device.get("mediamtx_path")),
                "viewer_url": self.text(device.get("viewer_url") or device.get("source")),
            },
        }
