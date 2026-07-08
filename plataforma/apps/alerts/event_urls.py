from django.urls import path

from apps.alerts.event_views import (
    EventHistoryFilterOptionsView,
    EventHistoryStatusView,
    EventHistoryView,
    EventMediaProxyView,
)

urlpatterns = [
    path("history/", EventHistoryView.as_view(), name="event-history"),
    path("history/filter-options/", EventHistoryFilterOptionsView.as_view(), name="event-history-filter-options"),
    path("history/<uuid:event_id>/status/", EventHistoryStatusView.as_view(), name="event-history-status"),
    path("media/crop/", EventMediaProxyView.as_view(), name="event-media-crop"),
    path("media/video/", EventMediaProxyView.as_view(), name="event-media-video"),
]
