from django.contrib import admin

from apps.streaming.models import StreamConfig, StreamPath


@admin.register(StreamPath)
class StreamPathAdmin(admin.ModelAdmin):
    list_display = ("path", "resource_type", "resource_id", "company", "active", "can_publish")
    list_filter = ("active", "can_publish", "resource_type", "company")
    search_fields = ("path", "resource_id")


@admin.register(StreamConfig)
class StreamConfigAdmin(admin.ModelAdmin):
    list_display = ("mediamtx_path", "camera", "drone", "stream_status", "active")
    list_filter = ("active", "stream_status", "input_protocol", "output_protocol")
    search_fields = ("mediamtx_path", "publish_path", "camera__name", "drone__name")
    readonly_fields = ("token_encrypted",)
