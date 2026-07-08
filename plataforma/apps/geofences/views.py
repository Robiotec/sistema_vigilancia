from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import ReadOnlyOrStaff
from apps.geofences.services import GeofenceAdminError, GeofenceAdminService


class GeofenceOverviewView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        try:
            return Response(GeofenceAdminService().overview(request.user))
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)


class GeofenceListView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        try:
            return Response(GeofenceAdminService().list_geofences(request.user))
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

    def post(self, request):
        try:
            geofence = GeofenceAdminService().create(request.user, request.data)
        except GeofenceAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "geofence": geofence}, status=status.HTTP_201_CREATED)


class GeofenceDetailView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def put(self, request, geofence_id):
        return self._save(request, geofence_id)

    def patch(self, request, geofence_id):
        return self._save(request, geofence_id)

    def delete(self, request, geofence_id):
        try:
            GeofenceAdminService().delete(request.user, str(geofence_id))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Geocerca no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True})

    def _save(self, request, geofence_id):
        try:
            geofence = GeofenceAdminService().update(request.user, str(geofence_id), request.data)
        except FileNotFoundError:
            return Response({"ok": False, "error": "Geocerca no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except GeofenceAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "geofence": geofence})


class GeofenceAlertListView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        processed = self._processed_filter(request.query_params.get("processed"))
        try:
            return Response(
                GeofenceAdminService().list_alerts(
                    request.user,
                    limit=int(request.query_params.get("limit") or 100),
                    processed=processed,
                )
            )
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

    @staticmethod
    def _processed_filter(value: str | None) -> bool | None:
        if value is None or value == "":
            return None
        return value.strip().lower() not in {"0", "false", "falso", "no", "off"}


class GeofenceAlertProcessedView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def patch(self, request, alert_id):
        processed = request.data.get("processed", True) if isinstance(request.data, dict) else True
        if not isinstance(processed, bool):
            processed = str(processed).strip().lower() not in {"0", "false", "falso", "no", "off"}
        try:
            alert = GeofenceAdminService().mark_alert_processed(request.user, str(alert_id), processed=processed)
        except FileNotFoundError:
            return Response({"ok": False, "error": "Alerta no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "alert": alert})
