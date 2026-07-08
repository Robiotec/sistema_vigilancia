"""URL configuration for the new Robiotec platform."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from apps.accounts.views import LoginView
from apps.core.health import HealthCheckView
from apps.frontend.views import (
    DashboardShellView,
    CameraViewerView,
    DeviceAdminView,
    DetectionReportsView,
    EventHistoryView,
    FleetKilometersView,
    FleetMapView,
    GeofenceAdminView,
    NotificationsView,
    OperationsView,
    ProfileView,
    UserAccessAdminView,
)

api_patterns = [
    path("health/", HealthCheckView.as_view(), name="api-health"),
    path("auth/", include("apps.accounts.urls")),
    path("accounts/", include("apps.accounts.admin_urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("devices/", include("apps.devices.urls")),
    path("fleet/", include("apps.fleet.urls")),
    path("geofences/", include("apps.geofences.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("events/", include("apps.alerts.event_urls")),
    path("reports/", include("apps.reports.urls")),
    path("streaming/", include("apps.streaming.urls")),
    path("operations/", include("apps.operations.urls")),
]

urlpatterns = [
    path("", DashboardShellView.as_view(), name="dashboard-shell"),
    path("login/", LoginView.as_view(), name="login-page"),
    path("camaras/", CameraViewerView.as_view(), name="camera-viewer"),
    path("administracion/dispositivos/", DeviceAdminView.as_view(), name="device-admin"),
    path("mapa/", FleetMapView.as_view(), name="fleet-map"),
    path("geocercas/", GeofenceAdminView.as_view(), name="geofence-admin"),
    path("eventos/", EventHistoryView.as_view(), name="event-history-page"),
    path("reportes/", DetectionReportsView.as_view(), name="detection-reports"),
    path("perfil/", ProfileView.as_view(), name="profile"),
    path("usuarios/", UserAccessAdminView.as_view(), name="user-access-admin"),
    path("gestion-kilometros/", FleetKilometersView.as_view(), name="fleet-kilometers"),
    path("notificaciones/", NotificationsView.as_view(), name="notifications"),
    path("servicios/", OperationsView.as_view(), name="operations"),
    path("admin/", admin.site.urls),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("api/v1/", include((api_patterns, "api"), namespace="api")),
]

if settings.ROBIOTEC_SERVE_STATIC_DIRECT:
    urlpatterns.append(
        path("static/<path:path>", serve, {"document_root": settings.STATIC_ROOT})
    )
