from rest_framework.routers import DefaultRouter

from django.urls import path

from apps.fleet.views import (
    ArcomConcessionLookupView,
    ArcomConcessionsView,
    DroneRouteView,
    FleetLatestLocationsView,
    OsintLayersView,
    VehicleRouteView,
    VehicleTelemetryViewSet,
)

router = DefaultRouter()
router.register("vehicle-telemetry", VehicleTelemetryViewSet, basename="vehicle-telemetry")

urlpatterns = [
    path("latest/", FleetLatestLocationsView.as_view(), name="fleet-latest"),
    path("vehicles/<uuid:vehicle_id>/route/", VehicleRouteView.as_view(), name="vehicle-route"),
    path("drones/<uuid:drone_id>/route/", DroneRouteView.as_view(), name="drone-route"),
    path("geointel/arcom/concessions/", ArcomConcessionsView.as_view(), name="geointel-arcom-concessions"),
    path("geointel/arcom/concession-lookup/", ArcomConcessionLookupView.as_view(), name="geointel-arcom-concession-lookup"),
    path("geointel/osint/layers/", OsintLayersView.as_view(), name="geointel-osint-layers"),
    *router.urls,
]
