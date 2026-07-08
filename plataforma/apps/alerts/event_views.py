from __future__ import annotations

import mimetypes

import requests
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.services import EventHistoryService
from apps.core.permissions import AlertRolePermission


class EventHistoryView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        return Response(EventHistoryService().list(request.query_params.dict()))


class EventHistoryFilterOptionsView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        try:
            return Response(EventHistoryService().filter_options(str(request.query_params.get("field", ""))))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class EventHistoryStatusView(APIView):
    permission_classes = [AlertRolePermission]

    def patch(self, request, event_id):
        try:
            return Response(EventHistoryService().update_status(str(event_id), str(request.data.get("status", ""))))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Evento no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class EventMediaProxyView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        path = str(request.query_params.get("path", "")).strip()
        if not path.startswith(("http://", "https://")):
            return Response({"ok": False, "error": "Ruta de media no valida"}, status=status.HTTP_404_NOT_FOUND)
        try:
            response = requests.get(path, stream=True, timeout=int(settings.ROBIOTEC_MEDIA_PROXY_TIMEOUT_SECONDS))
        except requests.RequestException as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        if response.status_code >= 400:
            response.close()
            return Response({"ok": False, "error": f"HTTP {response.status_code}"}, status=status.HTTP_404_NOT_FOUND)
        content_type = response.headers.get("Content-Type") or mimetypes.guess_type(path)[0] or "application/octet-stream"
        if request.path.endswith("/crop/"):
            content = response.content
            response.close()
            return HttpResponse(content, content_type=content_type, headers={"Cache-Control": "public, max-age=300"})
        return StreamingHttpResponse(
            _iter_response(response),
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=300"},
        )


def _iter_response(response):
    try:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                yield chunk
    finally:
        response.close()
