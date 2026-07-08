"""Health endpoints used by systemd, Nginx and monitors."""

from django.db import connection
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        database_ok = True
        database_error = None

        try:
            connection.ensure_connection()
        except Exception as exc:  # pragma: no cover - depends on runtime services
            database_ok = False
            database_error = str(exc)

        payload = {
            "service": "robiotec-django",
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "error",
        }
        if database_error:
            payload["database_error"] = database_error

        return Response(payload, status=200 if database_ok else 503)
