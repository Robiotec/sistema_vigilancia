from django.db import models


class FleetDailyReportSetting(models.Model):
    singleton_key = models.CharField(max_length=32, primary_key=True, default="default")
    enabled = models.BooleanField(default=False)
    send_time = models.CharField(max_length=5, default="07:00")
    recipients = models.JSONField(default=list)
    last_sent_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "fleet_daily_report_settings"

    def __str__(self) -> str:
        return "Reporte diario de flota"
