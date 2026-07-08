from django.contrib import admin

from apps.fleet.models import DroneTelemetry, VehicleTelemetry


@admin.register(VehicleTelemetry)
class VehicleTelemetryAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "latitude", "longitude", "speed", "received_at")
    list_filter = ("received_at",)
    search_fields = ("vehicle__plate", "vehicle__name")


@admin.register(DroneTelemetry)
class DroneTelemetryAdmin(admin.ModelAdmin):
    list_display = ("drone", "latitude", "longitude", "altitude", "battery", "received_at")
    list_filter = ("received_at",)
    search_fields = ("drone__name", "drone__unique_code")
