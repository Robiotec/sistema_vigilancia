from __future__ import annotations

from typing import Any

from back.app.config import Settings
from back.app.domain.drones.dji import DjiDroneNormalizer
from back.app.domain.drones.robiotec import RobiotecDroneNormalizer


class DroneNormalizerFactory:
    """Selecciona la clase hija correcta segun el proveedor del dron."""

    def __init__(self, settings: Settings) -> None:
        self.dji = DjiDroneNormalizer(settings)
        self.robiotec = RobiotecDroneNormalizer(settings)

    def item(
        self,
        drone: dict[str, Any],
        stream_config: dict[str, Any] | None = None,
        companies: dict[str, dict[str, Any]] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        provider = str(drone.get("provider") or drone.get("drone_type") or "robiotec").strip().lower()
        normalizer = self.dji if provider == "dji" else self.robiotec
        return normalizer.item(drone, stream_config, companies, users)
