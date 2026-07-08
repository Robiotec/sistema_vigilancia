from django.db import models

from apps.core.models import LegacyUuidModel


class NotificationEmailRecipient(LegacyUuidModel):
    email = models.EmailField(max_length=180)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "notification_email_recipients"
        ordering = ["email"]


class NotificationTelegramChat(LegacyUuidModel):
    chat_id = models.CharField(max_length=80)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "notification_telegram_chat_ids"
        ordering = ["chat_id"]


class CameraEventHistory(LegacyUuidModel):
    event_type = models.CharField(max_length=32)
    event_category = models.CharField(max_length=64, null=True, blank=True)
    origin = models.CharField(max_length=32, default="fixed_camera")
    camera_id = models.CharField(max_length=128)
    camera_name = models.CharField(max_length=160, null=True, blank=True)
    camera_location = models.TextField(null=True, blank=True)
    event_timestamp = models.BigIntegerField(null=True, blank=True)
    detected_at = models.DateTimeField()
    detected_date = models.DateField(null=True, blank=True)
    title = models.TextField()
    description = models.TextField(null=True, blank=True)
    person_id = models.CharField(max_length=64, null=True, blank=True)
    person_name = models.TextField(null=True, blank=True)
    plate = models.CharField(max_length=32, null=True, blank=True)
    track_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32)
    severity = models.CharField(max_length=32, null=True, blank=True)
    manifest_file_path = models.TextField(null=True, blank=True)
    json_file_path = models.TextField(null=True, blank=True)
    video_file_path = models.TextField(null=True, blank=True)
    image_file_path = models.TextField(null=True, blank=True)
    crop_path = models.TextField(null=True, blank=True)
    manifest_payload = models.JSONField(default=dict)
    detail_payload = models.JSONField(default=dict)
    event_uid = models.TextField()
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "camera_event_history"
        ordering = ["-detected_at"]
