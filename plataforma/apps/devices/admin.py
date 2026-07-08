from django.contrib import admin

from apps.devices.models import Camera, Drone, RBox, Vehicle


@admin.register(RBox)
class RBoxAdmin(admin.ModelAdmin):
    list_display = ("name", "serial", "company", "local_ip", "status", "active")
    list_filter = ("active", "status", "company")
    search_fields = ("name", "serial", "local_ip", "public_ip")


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "unique_code", "camera_type", "rbox", "vehicle", "active", "uses_rbox")
    list_filter = ("active", "uses_rbox", "camera_type", "company")
    search_fields = ("name", "unique_code", "ip", "brand")
    readonly_fields = ("password_encrypted",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate", "name", "vehicle_type", "company", "active")
    list_filter = ("active", "vehicle_type", "company")
    search_fields = ("plate", "name", "unique_code")


@admin.register(Drone)
class DroneAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "unique_code", "status", "active")
    list_filter = ("active", "status", "provider", "company")
    search_fields = ("name", "unique_code", "serial_number")
