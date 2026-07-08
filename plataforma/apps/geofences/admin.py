from django.contrib import admin

from apps.geofences.models import Geofence, GeofenceAlert, VehicleGeofenceState


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "geofence_type", "active")
    list_filter = ("active", "geofence_type", "company")
    search_fields = ("name", "description")


@admin.register(VehicleGeofenceState)
class VehicleGeofenceStateAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "geofence", "inside", "last_gps_at", "last_changed_at")
    list_filter = ("inside",)
    search_fields = ("vehicle__plate", "geofence__name")


@admin.register(GeofenceAlert)
class GeofenceAlertAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "plate", "geofence_name", "event_type", "recorded_at")
    list_filter = ("event_type", "processed", "recorded_at")
    search_fields = ("plate", "geofence_name", "vehicle__name")
