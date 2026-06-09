"""
Instancias globales (singletons) del dashboard.

Centraliza la creación de objetos de larga vida para que los routers
puedan importarlos sin crear dependencias circulares.
"""
from __future__ import annotations

from pathlib import Path

from back.app.config import get_settings
from back.app.core.helpers import DashboardHelper
from back.app.domain.cameras import CameraFormMapper, CameraNormalizer
from back.app.domain.device_catalog import DeviceCatalogBuilder
from back.app.domain.drones.factory import DroneNormalizerFactory
from back.app.domain.empresa import EmpresaMapper, EmpresaService
from back.app.domain.rbox import RBoxMapper
from back.app.domain.streaming import StreamConfigMapper
from back.app.domain.vehicles import VehicleNormalizer
from back.app.domain.vehicles.telemetry import VehicleTelemetryMapper
from back.app.services.api_client import DashboardApiClient
from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
from back.app.services.remote_detection_feed import RemoteDetectionFeedService
from back.app.services.rendering import DashboardTemplateRenderer

SESSION_COOKIE = "robiotec_dashboard_token"

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "front"
TEMPLATES = FRONT / "templates"
STATIC = FRONT / "static"

settings = get_settings()
api_client = DashboardApiClient(settings)
remote_detection_feed = RemoteDetectionFeedService(settings)
remote_clip_telegram_notifier = RemoteClipTelegramNotifier(settings)
helper = DashboardHelper(SESSION_COOKIE)
camera_normalizer = CameraNormalizer()
vehicle_normalizer = VehicleNormalizer()
drone_normalizer = DroneNormalizerFactory(settings)
device_catalog = DeviceCatalogBuilder(settings)
camera_form_mapper = CameraFormMapper(helper, settings)
empresa_mapper = EmpresaMapper()
rbox_mapper = RBoxMapper()
stream_config_mapper = StreamConfigMapper()
vehicle_telemetry_mapper = VehicleTelemetryMapper()
template_renderer = DashboardTemplateRenderer(TEMPLATES)


def _api_call(path: str, *, method: str = "GET", token: str | None = None, data=None):
    return api_client.request(path, method=method, token=token, data=data)


empresa_service = EmpresaService(_api_call)
