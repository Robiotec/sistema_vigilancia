from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import DeviceRolePermission
from apps.streaming.services import CameraViewerService


class CameraViewerCatalogView(APIView):
    permission_classes = [DeviceRolePermission]

    def get(self, request):
        return Response(CameraViewerService().catalog(request.user))


class CameraViewerSnapshotView(APIView):
    permission_classes = [DeviceRolePermission]

    def get(self, request, camera_id):
        mode = str(request.query_params.get("mode", "default") or "default")
        try:
            jpeg = CameraViewerService().snapshot(str(camera_id), request.user, mode=mode)
        except FileNotFoundError:
            return Response({"ok": False, "error": "Camara no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        if not jpeg:
            return Response({"ok": False, "error": "Video no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return HttpResponse(jpeg, content_type="image/jpeg", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        })


class CameraViewerEventsView(APIView):
    permission_classes = [DeviceRolePermission]

    def get(self, request, camera_id):
        try:
            limit = int(request.query_params.get("limit", 8) or 8)
        except (TypeError, ValueError):
            limit = 8
        try:
            return Response(CameraViewerService().camera_events(str(camera_id), request.user, limit=limit))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Camara no encontrada"}, status=status.HTTP_404_NOT_FOUND)


class CameraViewerInferenceView(APIView):
    permission_classes = [DeviceRolePermission]

    def patch(self, request, camera_id):
        inference_type = str(request.data.get("inference_type", "inactiva") or "inactiva")
        try:
            return Response(CameraViewerService().set_inference_type(str(camera_id), inference_type, request.user))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Camara no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
