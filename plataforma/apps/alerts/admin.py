from django.contrib import admin

from apps.alerts.models import (
    CameraEventHistory,
    NotificationEmailRecipient,
    NotificationTelegramChat,
)


@admin.register(NotificationEmailRecipient)
class NotificationEmailRecipientAdmin(admin.ModelAdmin):
    list_display = ("email", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("email",)


@admin.register(NotificationTelegramChat)
class NotificationTelegramChatAdmin(admin.ModelAdmin):
    list_display = ("chat_id", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("chat_id",)


@admin.register(CameraEventHistory)
class CameraEventHistoryAdmin(admin.ModelAdmin):
    list_display = ("title", "camera_name", "event_type", "origin", "status", "detected_at")
    list_filter = ("origin", "event_type", "status", "severity", "detected_at")
    search_fields = ("title", "camera_name", "camera_id", "plate", "person_name")
