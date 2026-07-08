from django.urls import path

from apps.streaming.views import (
    CameraViewerCatalogView,
    CameraViewerEventsView,
    CameraViewerInferenceView,
    CameraViewerSnapshotView,
)

urlpatterns = [
    path("camera-viewer/", CameraViewerCatalogView.as_view(), name="camera-viewer-catalog"),
    path("camera-viewer/<uuid:camera_id>/events/", CameraViewerEventsView.as_view(), name="camera-viewer-events"),
    path("camera-viewer/<uuid:camera_id>/inference/", CameraViewerInferenceView.as_view(), name="camera-viewer-inference"),
    path("camera-viewer/<uuid:camera_id>/snapshot/", CameraViewerSnapshotView.as_view(), name="camera-viewer-snapshot"),
]
