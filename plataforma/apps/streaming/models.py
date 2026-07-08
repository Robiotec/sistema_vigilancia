from django.db import models

from apps.core.models import LegacyTimestampMixin, LegacyUuidModel
from apps.devices.models import Camera, Drone
from apps.organizations.models import Area, Company


class StreamPath(LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="stream_paths",
    )
    area = models.ForeignKey(
        Area,
        db_column="area_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="stream_paths",
    )
    path = models.CharField(max_length=180)
    resource_type = models.CharField(max_length=40)
    resource_id = models.UUIDField()
    active = models.BooleanField(default=True)
    can_publish = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "stream_paths"
        ordering = ["path"]

    def __str__(self) -> str:
        return self.path


class StreamConfig(LegacyTimestampMixin, LegacyUuidModel):
    camera = models.ForeignKey(
        Camera,
        db_column="camera_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="stream_configs",
    )
    drone = models.ForeignKey(
        Drone,
        db_column="drone_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="stream_configs",
    )
    input_protocol = models.CharField(max_length=40, default="rtsp")
    origin_url = models.TextField(null=True, blank=True)
    mediamtx_path = models.CharField(max_length=180)
    output_webrtc_url = models.TextField(null=True, blank=True)
    output_rtsp_url = models.TextField(null=True, blank=True)
    output_hls_url = models.TextField(null=True, blank=True)
    publish_path = models.CharField(max_length=120, null=True, blank=True)
    publish_url = models.TextField(null=True, blank=True)
    output_protocol = models.CharField(max_length=40, default="webrtc")
    mediamtx_server = models.CharField(max_length=160, null=True, blank=True)
    mediamtx_port = models.IntegerField(null=True, blank=True)
    token_encrypted = models.TextField(null=True, blank=True)
    stream_status = models.CharField(max_length=40, default="pendiente")
    webrtc_enabled = models.BooleanField(default=True)
    rtsp_enabled = models.BooleanField(default=True)
    rtmp_enabled = models.BooleanField(default=False)
    requires_token = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "stream_configs"
        ordering = ["mediamtx_path"]

    def __str__(self) -> str:
        return self.mediamtx_path
