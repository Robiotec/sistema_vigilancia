from django.urls import path

from apps.geofences.views import (
    GeofenceAlertListView,
    GeofenceAlertProcessedView,
    GeofenceDetailView,
    GeofenceListView,
    GeofenceOverviewView,
)

urlpatterns = [
    path("overview/", GeofenceOverviewView.as_view(), name="geofence-overview"),
    path("geofences/", GeofenceListView.as_view(), name="geofence-list"),
    path("geofences/<uuid:geofence_id>/", GeofenceDetailView.as_view(), name="geofence-detail"),
    path("alerts/", GeofenceAlertListView.as_view(), name="geofence-alert-list"),
    path("alerts/<uuid:alert_id>/processed/", GeofenceAlertProcessedView.as_view(), name="geofence-alert-processed"),
]
