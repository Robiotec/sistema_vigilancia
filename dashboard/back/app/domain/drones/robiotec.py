from __future__ import annotations

from back.app.domain.drones.base import BaseDroneNormalizer


class RobiotecDroneNormalizer(BaseDroneNormalizer):
    """Normalizador específico para Dron Robiotec."""

    vehicle_type_code = "drone_robiotec"
    vehicle_type_name = "Dron Robiotec"
    manufacturer = "Robiotec"
    telemetry_mode = "api"
