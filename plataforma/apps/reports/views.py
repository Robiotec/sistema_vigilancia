from __future__ import annotations

import csv
import io

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import ReportAdminPermission, ReportRolePermission
from apps.reports.analytics import DetectionReportService
from apps.reports.services import DailyFleetReportService, FleetReportSettingsService


class DailyFleetReportView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        report = DailyFleetReportService().build(request.query_params.get("date"))
        return Response(report.as_dict())


class DailyFleetReportPdfView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        report = DailyFleetReportService().build(request.query_params.get("date"))
        pdf = DailyFleetReportService().build_pdf(report)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="reporte_flota_{report.date.isoformat()}.pdf"'
        return response


class DailyFleetReportSettingsView(APIView):
    permission_classes = [ReportAdminPermission]

    def get(self, request):
        return Response({"ok": True, "settings": FleetReportSettingsService().load()})

    def put(self, request):
        settings = FleetReportSettingsService().save(request.data if isinstance(request.data, dict) else {})
        return Response({"ok": True, "settings": settings})


class DailyFleetReportSendNowView(APIView):
    permission_classes = [ReportAdminPermission]

    def post(self, request):
        source = request.data if isinstance(request.data, dict) else {}
        try:
            result = DailyFleetReportService().send_for_date(
                source.get("date") or source.get("report_date"),
                recipients=source.get("recipients"),
                mark_sent=False,
            )
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class DetectionReportCamerasView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        return Response({"items": DetectionReportService().cameras()})


class DetectionReportOverviewView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        try:
            payload = DetectionReportService().overview(**_range_params(request))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class DetectionPersonnelDailyView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        try:
            rows = DetectionReportService().personnel_daily(
                **_range_params(request),
                gap_minutes=_gap(request),
            )
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if _wants_csv(request):
            return _csv_response(
                "personal_diario.csv",
                ["Cedula", "Nombre", "Fecha", "Entrada", "Salida", "Horas", "Sesiones", "Reingresos", "Detecciones", "Camaras"],
                rows,
                ["person_id", "person_name", "work_date", "first_seen", "last_seen", "hours", "sessions", "reentries", "detections", "cameras"],
            )
        return Response({"items": rows, "total": len(rows)})


class DetectionPersonnelIndividualView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        person_id = str(request.query_params.get("person_id", "")).strip()
        if not person_id:
            return Response({"ok": False, "error": "person_id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows = DetectionReportService().personnel_daily(
                **_range_params(request),
                gap_minutes=_gap(request),
                person_id=person_id,
            )
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"items": rows, "total": len(rows)})


class DetectionPersonnelSessionsView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        person_id = str(request.query_params.get("person_id", "")).strip()
        if not person_id:
            return Response({"ok": False, "error": "person_id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows = DetectionReportService().personnel_sessions(
                **_range_params(request),
                person_id=person_id,
                work_date=str(request.query_params.get("work_date", "")).strip(),
                gap_minutes=_gap(request),
            )
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if _wants_csv(request):
            return _csv_response(
                "personal_sesiones.csv",
                ["Cedula", "Nombre", "Fecha", "Sesion", "Entrada", "Salida", "Minutos sesion", "Minutos fuera", "Detecciones", "Camaras"],
                rows,
                ["person_id", "person_name", "work_date", "session_no", "entry_at", "exit_at", "minutes_inside_session", "minutes_since_previous_exit", "detections", "cameras"],
            )
        return Response({"items": rows, "total": len(rows)})


class DetectionPersonnelMonthlyView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        try:
            rows = DetectionReportService().personnel_monthly(
                year=int(request.query_params.get("year", 0) or 0),
                month=int(request.query_params.get("month", 0) or 0),
                gap_minutes=_gap(request),
                camera_id=str(request.query_params.get("camera_id", "")).strip(),
            )
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if _wants_csv(request):
            return _csv_response(
                "personal_mensual.csv",
                ["Cedula", "Nombre", "Dias", "Horas", "Promedio", "Sesiones", "Reingresos", "Detecciones"],
                rows,
                ["person_id", "person_name", "days_present", "total_hours", "avg_hours_day", "sessions", "reentries", "detections"],
            )
        return Response({"items": rows, "total": len(rows)})


class DetectionPlatesView(APIView):
    permission_classes = [ReportRolePermission]

    def get(self, request):
        try:
            rows = DetectionReportService().plates(**_range_params(request))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if _wants_csv(request):
            return _csv_response(
                "placas.csv",
                ["Placa", "Camara", "Detecciones", "Dias", "Primera", "Ultima"],
                rows,
                ["plate", "camera_name", "detections", "days_detected", "first_seen", "last_seen"],
            )
        return Response({"items": rows, "total": len(rows)})


def _range_params(request) -> dict[str, str]:
    return {
        "from_date": str(request.query_params.get("from_date", "")).strip(),
        "to_date": str(request.query_params.get("to_date", "")).strip(),
        "camera_id": str(request.query_params.get("camera_id", "")).strip(),
    }


def _gap(request) -> int:
    try:
        return int(request.query_params.get("gap_minutes", 15) or 15)
    except (TypeError, ValueError):
        return 15


def _wants_csv(request) -> bool:
    return str(request.query_params.get("format", "")).lower() == "csv"


def _csv_response(filename: str, headers: list[str], rows: list[dict[str, object]], keys: list[str]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(key, "") for key in keys])
    response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
