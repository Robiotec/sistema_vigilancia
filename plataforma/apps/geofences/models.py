from django.db import models

from apps.core.models import LegacyTimestampMixin, LegacyUuidModel
from apps.devices.models import Vehicle
from apps.organizations.models import Company


class Geofence(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="geofences",
    )
    name = models.CharField(max_length=160)
    geofence_type = models.CharField(max_length=20)
    geometry = models.JSONField(default=dict)
    active = models.BooleanField(default=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "geofences"
        ordering = ["name"]


class VehicleGeofenceState(LegacyUuidModel):
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="vehicle_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="geofence_states",
    )
    geofence = models.ForeignKey(
        Geofence,
        db_column="geofence_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="vehicle_states",
    )
    inside = models.BooleanField(default=False)
    last_gps_at = models.DateTimeField(null=True, blank=True)
    last_changed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "vehicle_geofence_states"
        unique_together = [("vehicle", "geofence")]


class GeofenceAlert(LegacyUuidModel):
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="vehicle_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="geofence_alerts",
    )
    plate = models.CharField(max_length=40, null=True, blank=True)
    geofence = models.ForeignKey(
        Geofence,
        db_column="geofence_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="alerts",
    )
    geofence_name = models.CharField(max_length=160)
    event_type = models.CharField(max_length=20)
    gps_at = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    processed = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)

    class Meta:
        managed = False
        db_table = "geofence_alerts"
        ordering = ["-recorded_at"]
