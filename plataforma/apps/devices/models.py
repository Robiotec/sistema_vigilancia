from django.db import models

from apps.accounts.models import LegacyUser
from apps.core.models import LegacyTimestampMixin, LegacyUuidModel
from apps.organizations.models import Area, Company


class RBox(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="rboxes",
    )
    area = models.ForeignKey(
        Area,
        db_column="area_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="rboxes",
    )
    name = models.CharField(max_length=160)
    serial = models.CharField(max_length=120)
    local_ip = models.CharField(max_length=120, null=True, blank=True)
    public_ip = models.CharField(max_length=120, null=True, blank=True)
    server_ip = models.CharField(max_length=120, null=True, blank=True)
    server_port = models.IntegerField(null=True, blank=True)
    location = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=40, default="activo")
    last_connection_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "rboxes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Vehicle(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="vehicles",
    )
    area = models.ForeignKey(
        Area,
        db_column="area_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    owner_user = models.ForeignKey(
        LegacyUser,
        db_column="owner_user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    name = models.CharField(max_length=160)
    vehicle_type = models.CharField(max_length=60, default="auto")
    vehicle_subtype = models.CharField(max_length=60, null=True, blank=True)
    unique_code = models.CharField(max_length=120, null=True, blank=True)
    plate = models.CharField(max_length=40, null=True, blank=True)
    brand = models.CharField(db_column="make", max_length=100, null=True, blank=True)
    model = models.CharField(max_length=100, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    driver_name = models.CharField(max_length=160, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)
    can_publish = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "vehicles"
        ordering = ["plate", "name"]

    def __str__(self) -> str:
        return self.plate or self.name


class Drone(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="drones",
    )
    area = models.ForeignKey(
        Area,
        db_column="area_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="drones",
    )
    owner_user = models.ForeignKey(
        LegacyUser,
        db_column="owner_user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="drones",
    )
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=60, default="robiotec")
    unique_code = models.CharField(max_length=120, null=True, blank=True)
    drone_type = models.CharField(max_length=60, default="robiotec")
    model = models.CharField(max_length=100, null=True, blank=True)
    manufacturer = models.CharField(max_length=100, null=True, blank=True)
    serial_number = models.CharField(max_length=160, null=True, blank=True)
    status = models.CharField(max_length=40, default="activo")
    active = models.BooleanField(default=True)
    can_publish = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "drones"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Camera(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="cameras",
    )
    area = models.ForeignKey(
        Area,
        db_column="area_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="cameras",
    )
    rbox = models.ForeignKey(
        RBox,
        db_column="rbox_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="cameras",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="vehicle_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="cameras",
    )
    drone = models.ForeignKey(
        Drone,
        db_column="drone_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="cameras",
    )
    name = models.CharField(max_length=160)
    brand = models.CharField(max_length=60)
    model = models.CharField(max_length=80, null=True, blank=True)
    rtsp_url = models.TextField(null=True, blank=True)
    unique_code = models.CharField(max_length=120, null=True, blank=True)
    camera_type = models.CharField(max_length=40, default="fixed")
    inference_type = models.CharField(max_length=40, default="inactiva")
    protocol = models.CharField(max_length=40, default="rtsp")
    ip = models.CharField(max_length=120, null=True, blank=True)
    port = models.IntegerField(null=True, blank=True)
    username = models.CharField(max_length=120, null=True, blank=True)
    password_encrypted = models.TextField(null=True, blank=True)
    channel = models.IntegerField(null=True, blank=True)
    stream = models.IntegerField(null=True, blank=True)
    quality = models.CharField(max_length=40, null=True, blank=True)
    vehicle_position = models.CharField(max_length=120, null=True, blank=True)
    public_ip_enabled = models.BooleanField(default=False)
    uses_rbox = models.BooleanField(default=False)
    notification_telegram = models.BooleanField(default=True)
    notification_email = models.BooleanField(default=True)
    status = models.CharField(max_length=40, default="activo")
    active = models.BooleanField(default=True)
    can_publish = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "cameras"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
