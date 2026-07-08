from django.urls import path

from apps.reports.views import (
    DailyFleetReportPdfView,
    DailyFleetReportSendNowView,
    DailyFleetReportSettingsView,
    DailyFleetReportView,
    DetectionPersonnelDailyView,
    DetectionPersonnelIndividualView,
    DetectionPersonnelMonthlyView,
    DetectionPersonnelSessionsView,
    DetectionPlatesView,
    DetectionReportCamerasView,
    DetectionReportOverviewView,
)

urlpatterns = [
    path("fleet-daily/", DailyFleetReportView.as_view(), name="fleet-daily-report"),
    path("fleet-daily/pdf/", DailyFleetReportPdfView.as_view(), name="fleet-daily-report-pdf"),
    path("fleet-daily/settings/", DailyFleetReportSettingsView.as_view(), name="fleet-daily-report-settings"),
    path("fleet-daily/send-now/", DailyFleetReportSendNowView.as_view(), name="fleet-daily-report-send-now"),
    path("detection/cameras/", DetectionReportCamerasView.as_view(), name="detection-report-cameras"),
    path("detection/overview/", DetectionReportOverviewView.as_view(), name="detection-report-overview"),
    path("detection/personnel/daily/", DetectionPersonnelDailyView.as_view(), name="detection-personnel-daily"),
    path("detection/personnel/individual/", DetectionPersonnelIndividualView.as_view(), name="detection-personnel-individual"),
    path("detection/personnel/sessions/", DetectionPersonnelSessionsView.as_view(), name="detection-personnel-sessions"),
    path("detection/personnel/monthly/", DetectionPersonnelMonthlyView.as_view(), name="detection-personnel-monthly"),
    path("detection/plates/", DetectionPlatesView.as_view(), name="detection-plates"),
]
