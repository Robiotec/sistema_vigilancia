from django.db import models
from django.utils import timezone

from apps.core.models import LegacyUuidModel
from apps.devices.models import Drone, Vehicle


class VehicleTelemetry(LegacyUuidModel):
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="vehicle_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="telemetry",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "vehicle_telemetry"
        ordering = ["-received_at"]


class DroneTelemetry(LegacyUuidModel):
    drone = models.ForeignKey(
        Drone,
        db_column="drone_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="telemetry",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    battery = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    armed_state = models.CharField(max_length=80, null=True, blank=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "drone_telemetry"
        ordering = ["-received_at"]


class VehicleRouteSegment(LegacyUuidModel):
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="vehicle_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    from_telemetry = models.ForeignKey(
        VehicleTelemetry,
        db_column="from_telemetry_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    to_telemetry = models.ForeignKey(
        VehicleTelemetry,
        db_column="to_telemetry_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    local_day = models.DateField(db_index=True)
    segment_kind = models.CharField(max_length=24, default="raw")
    segment_reason = models.CharField(max_length=80, null=True, blank=True)
    distance_km = models.FloatField(default=0)
    elapsed_seconds = models.FloatField(default=0)
    implied_speed_kmh = models.FloatField(default=0)
    confidence = models.FloatField(null=True, blank=True)
    geometry = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "vehicle_route_segments"
        constraints = [
            models.UniqueConstraint(fields=["vehicle", "to_telemetry"], name="uq_vehicle_route_segment_to_point"),
        ]
        indexes = [
            models.Index(fields=["vehicle", "local_day"], name="ix_route_segments_vehicle_day"),
            models.Index(fields=["local_day", "segment_kind"], name="ix_route_segments_day_kind"),
        ]
