from __future__ import annotations

import json
import re
import smtplib
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.alerts.services import AlertRecipientService
from apps.devices.models import Vehicle
from apps.fleet.models import VehicleTelemetry
from apps.fleet.services import (
    ROUTE_SEGMENT_MAX_DISTANCE_KM,
    ROUTE_SEGMENT_MAX_GAP_SECONDS,
    ROUTE_SEGMENT_MAX_SPEED_KMH,
    VehicleKilometerService,
)
from apps.geofences.models import GeofenceAlert
from apps.reports.models import FleetDailyReportSetting

DEFAULT_SEND_TIME = "07:00"
SUBTYPE_LABELS = {
    "volqueta": "Volqueta",
    "camion": "Camion",
    "camioneta": "Camioneta",
    "retroexcavadora": "Retroexcavadora",
    "otra": "Otra",
    "sin_especificar": "Sin especificar",
}


@dataclass(frozen=True)
class DailyFleetReport:
    date: date
    generated_at: datetime
    totals: dict[str, object]
    vehicles: list[dict[str, object]]
    geofence_intervals: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "totals": self.totals,
            "vehicles": self.vehicles,
            "geofence_intervals": self.geofence_intervals,
        }


class FleetReportSettingsService:
    def load(self) -> dict[str, object]:
        setting = self._setting()
        return {
            "enabled": setting.enabled,
            "send_time": _parse_send_time(setting.send_time),
            "recipients": _normalize_recipients(setting.recipients),
            "fallback_recipients": AlertRecipientService().active_emails(),
            "last_sent_date": setting.last_sent_date.isoformat() if setting.last_sent_date else "",
            "updated_at": setting.updated_at.isoformat() if setting.updated_at else "",
        }

    def save(self, payload: dict[str, object] | None) -> dict[str, object]:
        source = payload if isinstance(payload, dict) else {}
        setting = self._setting()
        setting.enabled = bool(source.get("enabled"))
        setting.send_time = _parse_send_time(source.get("send_time"))
        setting.recipients = _normalize_recipients(source.get("recipients"))
        setting.updated_at = timezone.now()
        setting.save(update_fields=["enabled", "send_time", "recipients", "updated_at"])
        return self.load()

    def mark_sent(self, report_date: date) -> None:
        setting = self._setting()
        setting.last_sent_date = report_date
        setting.updated_at = timezone.now()
        setting.save(update_fields=["last_sent_date", "updated_at"])

    def _setting(self) -> FleetDailyReportSetting:
        self.ensure_table()
        setting, _created = FleetDailyReportSetting.objects.get_or_create(
            singleton_key="default",
            defaults={
                "enabled": False,
                "send_time": DEFAULT_SEND_TIME,
                "recipients": [],
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
            },
        )
        return setting

    @staticmethod
    def ensure_table() -> None:
        table_name = FleetDailyReportSetting._meta.db_table
        if table_name in connection.introspection.table_names():
            return
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fleet_daily_report_settings (
                        singleton_key varchar(32) PRIMARY KEY DEFAULT 'default',
                        enabled boolean NOT NULL DEFAULT false,
                        send_time varchar(5) NOT NULL DEFAULT '07:00',
                        recipients jsonb NOT NULL DEFAULT '[]'::jsonb,
                        last_sent_date date,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        updated_at timestamptz NOT NULL DEFAULT now(),
                        CONSTRAINT ck_fleet_daily_report_singleton CHECK (singleton_key = 'default')
                    );
                    INSERT INTO fleet_daily_report_settings (singleton_key)
                    VALUES ('default')
                    ON CONFLICT (singleton_key) DO NOTHING;
                    """
                )
            return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(FleetDailyReportSetting)


class DailyFleetReportService:
    def build(self, report_date: date | str | None = None) -> DailyFleetReport:
        target_day = _parse_date(report_date)
        vehicles = self._daily_vehicle_rows(target_day)
        intervals = self._geofence_intervals(target_day)
        intervals_by_vehicle: dict[str, list[dict[str, object]]] = defaultdict(list)
        for interval in intervals:
            intervals_by_vehicle[str(interval.get("vehicle_id") or "")].append(interval)
        for vehicle in vehicles:
            vehicle["geofence_intervals"] = intervals_by_vehicle.get(str(vehicle.get("vehicle_id") or ""), [])

        totals = {
            "total_km": round(sum(float(item.get("total_km") or 0) for item in vehicles), 2),
            "active_vehicles": sum(1 for item in vehicles if float(item.get("total_km") or 0) > 0.05),
            "total_vehicles": len(vehicles),
            "total_points": sum(int(item.get("total_points") or 0) for item in vehicles),
            "geofence_intervals": len(intervals),
            "geofence_minutes": round(sum(float(item.get("duration_minutes") or 0) for item in intervals), 1),
        }
        return DailyFleetReport(
            date=target_day,
            generated_at=timezone.localtime(),
            totals=totals,
            vehicles=vehicles,
            geofence_intervals=intervals,
        )

    def build_pdf(self, report: DailyFleetReport | dict[str, object]) -> bytes:
        payload = report.as_dict() if isinstance(report, DailyFleetReport) else report
        return build_fleet_report_pdf(payload)

    def send_for_date(
        self,
        report_date: date | str | None = None,
        *,
        recipients: list[str] | str | None = None,
        mark_sent: bool = False,
    ) -> dict[str, object]:
        target_day = _parse_date(report_date)
        settings_service = FleetReportSettingsService()
        configured = settings_service.load()
        target_recipients = _normalize_recipients(recipients)
        if not target_recipients:
            target_recipients = _normalize_recipients(configured.get("recipients"))
        if not target_recipients:
            target_recipients = _normalize_recipients(configured.get("fallback_recipients"))
        if not target_recipients:
            raise ValueError("No hay correos configurados para el reporte diario.")

        report = self.build(target_day)
        pdf_bytes = self.build_pdf(report)
        sent = EmailSender().send(
            {
                **NotificationSettingsService().email_settings(),
                "recipients": target_recipients,
                "subject": f"Reporte diario de flota - {target_day.isoformat()}",
                "message": (
                    "Adjunto se envia el reporte diario de flota en PDF.\n\n"
                    f"Fecha operativa: {target_day.isoformat()}\n"
                    f"Km totales: {float(report.totals.get('total_km') or 0):.2f}\n"
                    f"Vehiculos activos: {report.totals.get('active_vehicles')} / {report.totals.get('total_vehicles')}\n"
                ),
                "attachments": [
                    {
                        "filename": f"reporte_flota_{target_day.isoformat()}.pdf",
                        "content": pdf_bytes,
                        "mime_type": "application/pdf",
                    }
                ],
            }
        )
        if mark_sent:
            settings_service.mark_sent(target_day)
        return {
            "ok": True,
            "date": target_day.isoformat(),
            "sent": sent,
            "total": len(sent),
            "report": {
                "totals": report.totals,
                "vehicles": len(report.vehicles),
                "geofence_intervals": len(report.geofence_intervals),
            },
        }

    def check_schedule(self, *, now: datetime | None = None) -> dict[str, object]:
        current = timezone.localtime(now or timezone.now())
        settings_service = FleetReportSettingsService()
        configured = settings_service.load()
        report_date = current.date() - timedelta(days=1)
        if not configured.get("enabled"):
            return {"ok": True, "sent": [], "skipped": "disabled", "date": report_date.isoformat()}
        if str(configured.get("last_sent_date") or "") >= report_date.isoformat():
            return {"ok": True, "sent": [], "skipped": "already_sent", "date": report_date.isoformat()}
        if current.time() < _time_from_text(str(configured.get("send_time") or DEFAULT_SEND_TIME)):
            return {"ok": True, "sent": [], "skipped": "not_due", "date": report_date.isoformat()}
        return self.send_for_date(report_date, mark_sent=True)

    def _daily_vehicle_rows(self, report_date: date) -> list[dict[str, object]]:
        groups = self._logical_vehicle_groups()
        local_start, local_end = _local_bounds(report_date)
        query_start = local_start.astimezone(datetime_timezone.utc) - timedelta(days=1)
        query_end = local_end.astimezone(datetime_timezone.utc) + timedelta(days=1)
        rows: list[dict[str, object]] = []
        for group in groups:
            telemetry = list(
                VehicleTelemetry.objects.filter(
                    vehicle_id__in=group["source_vehicle_ids"],
                    received_at__gte=query_start,
                    received_at__lt=query_end,
                )
                .exclude(latitude__isnull=True)
                .exclude(longitude__isnull=True)
                .order_by("received_at", "id")
            )
            points = [
                self._telemetry_point(item)
                for item in telemetry
                if _valid_coordinates(item.latitude, item.longitude)
                and _local_date(self._gps_time(item)) == report_date
            ]
            points.sort(key=lambda point: (point["gps_at"], point["received_at"], point["id"]))
            total_km, max_speed = self._total_km(points)
            first = points[0] if points else {}
            last = points[-1] if points else {}
            rows.append(
                {
                    **group,
                    "source_vehicle_ids": [str(value) for value in group["source_vehicle_ids"]],
                    "source_count": len(group["source_vehicle_ids"]),
                    "total_km": round(total_km, 2),
                    "total_points": len(points),
                    "max_speed": round(max_speed, 1),
                    "active_days": 1 if total_km > 0.05 else 0,
                    "start_at": _iso(first.get("gps_at")),
                    "start_lat": first.get("latitude"),
                    "start_lon": first.get("longitude"),
                    "end_at": _iso(last.get("gps_at")),
                    "end_lat": last.get("latitude"),
                    "end_lon": last.get("longitude"),
                    "geofence_intervals": [],
                }
            )
        rows.sort(key=lambda item: (-float(item.get("total_km") or 0), str(item.get("label") or "")))
        return rows

    def _logical_vehicle_groups(self) -> list[dict[str, object]]:
        groups: dict[str, dict[str, object]] = {}
        vehicles = (
            Vehicle.objects.filter(active=True)
            .exclude(vehicle_type__istartswith="drone")
            .order_by("plate", "name")
        )
        for vehicle in vehicles:
            key = _fleet_key(vehicle)
            group = groups.setdefault(
                key,
                {
                    "vehicle_id": key,
                    "label": _vehicle_label(vehicle),
                    "plate": vehicle.plate or _vehicle_label(vehicle),
                    "brand": vehicle.brand or "",
                    "model": vehicle.model or "",
                    "year": vehicle.year,
                    "driver_name": vehicle.driver_name or "",
                    "chofer": vehicle.driver_name or "",
                    "vehicle_type": vehicle.vehicle_type or "",
                    "vehicle_subtype": vehicle.vehicle_subtype or "",
                    "vehicle_subtype_name": _vehicle_subtype_label(vehicle.vehicle_subtype),
                    "source_vehicle_ids": [],
                },
            )
            if not group.get("brand") and vehicle.brand:
                group["brand"] = vehicle.brand
            if not group.get("model") and vehicle.model:
                group["model"] = vehicle.model
            if not group.get("year") and vehicle.year:
                group["year"] = vehicle.year
            group["source_vehicle_ids"].append(vehicle.id)
        return list(groups.values())

    def _telemetry_point(self, telemetry: VehicleTelemetry) -> dict[str, object]:
        gps_at = self._gps_time(telemetry)
        return {
            "id": str(telemetry.id),
            "latitude": telemetry.latitude,
            "longitude": telemetry.longitude,
            "speed": telemetry.speed or 0,
            "received_at": telemetry.received_at,
            "gps_at": gps_at,
        }

    def _gps_time(self, telemetry: VehicleTelemetry) -> datetime:
        payload = telemetry.payload if isinstance(telemetry.payload, dict) else {}
        raw_value = payload.get("gps_datetime_iso") or payload.get("gps_at")
        if raw_value:
            try:
                parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime_timezone.utc)
            except ValueError:
                pass
        return telemetry.received_at

    def _total_km(self, points: list[dict[str, object]]) -> tuple[float, float]:
        total = 0.0
        max_speed = 0.0
        previous: dict[str, object] | None = None
        for point in points:
            max_speed = max(max_speed, float(point.get("speed") or 0))
            if previous is None:
                previous = point
                continue
            elapsed = max((point["gps_at"] - previous["gps_at"]).total_seconds(), 0)
            distance = VehicleKilometerService._haversine_km(
                float(previous["latitude"]),
                float(previous["longitude"]),
                float(point["latitude"]),
                float(point["longitude"]),
            )
            implied_speed = (distance / elapsed * 3600) if elapsed > 0 else 0
            if (
                0 < elapsed <= ROUTE_SEGMENT_MAX_GAP_SECONDS
                and distance <= ROUTE_SEGMENT_MAX_DISTANCE_KM
                and implied_speed <= ROUTE_SEGMENT_MAX_SPEED_KMH
            ):
                total += distance
            previous = point
        return total, max_speed

    def _geofence_intervals(self, report_date: date) -> list[dict[str, object]]:
        groups = self._logical_vehicle_groups()
        source_map: dict[str, dict[str, object]] = {}
        for group in groups:
            for source_id in group["source_vehicle_ids"]:
                source_map[str(source_id)] = group
        if not source_map:
            return []

        local_start, local_end = _local_bounds(report_date)
        alerts = list(
            GeofenceAlert.objects.filter(
                vehicle_id__in=list(source_map),
                recorded_at__lt=local_end.astimezone(datetime_timezone.utc),
            ).order_by("recorded_at", "id")
        )
        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for alert in alerts:
            group = source_map.get(str(alert.vehicle_id))
            if not group:
                continue
            event_at = alert.gps_at or alert.recorded_at
            if not event_at or event_at >= local_end.astimezone(datetime_timezone.utc):
                continue
            item = {
                **group,
                "source_vehicle_id": str(alert.vehicle_id),
                "geofence_id": str(alert.geofence_id),
                "geofence_name": alert.geofence_name or "Geocerca",
                "event_type": str(alert.event_type or "").lower(),
                "event_at": event_at,
                "is_previous": event_at < local_start.astimezone(datetime_timezone.utc),
            }
            grouped[(str(group["vehicle_id"]), str(alert.geofence_id))].append(item)

        intervals: list[dict[str, object]] = []
        for (_vehicle_id, _geofence_id), items in grouped.items():
            items.sort(key=lambda item: (item["event_at"], bool(item["is_previous"])))
            previous = next((item for item in reversed(items) if item["is_previous"]), None)
            day_events = [item for item in items if not item["is_previous"]]
            inside = str(previous.get("event_type") if previous else "") == "entry"
            entry_at = local_start if inside else None
            template = previous or (day_events[0] if day_events else {})
            group_intervals: list[dict[str, object]] = []

            for event in day_events:
                event_local = timezone.localtime(event["event_at"])
                event_type = str(event.get("event_type") or "")
                template = event
                if event_type == "entry":
                    inside = True
                    entry_at = max(event_local, local_start)
                elif event_type == "exit":
                    if inside:
                        start = entry_at or local_start
                        end = min(event_local, local_end)
                        if end > start:
                            group_intervals.append(_geofence_interval_item(template, start, end, "salio"))
                    elif group_intervals:
                        _extend_last_geofence_interval(group_intervals[-1], min(event_local, local_end))
                    inside = False
                    entry_at = None
            if inside:
                start = entry_at or local_start
                if local_end > start:
                    group_intervals.append(_geofence_interval_item(template, start, local_end, "permanece"))
            intervals.extend(group_intervals)

        intervals = _resolve_vehicle_geofence_overlaps(intervals)
        intervals.sort(key=_geofence_interval_sort_key)
        return intervals


class NotificationSettingsService:
    def email_settings(self) -> dict[str, object]:
        payload = self._payload()
        email = payload.get("email") if isinstance(payload.get("email"), dict) else {}
        return {
            "sender_email": str(email.get("sender_email") or "").strip(),
            "sender_password": str(email.get("sender_password") or "").strip(),
            "smtp_host": str(email.get("smtp_host") or "smtp.office365.com").strip(),
            "smtp_port": int(email.get("smtp_port") or 587),
        }

    def _payload(self) -> dict[str, object]:
        path = Path(
            getattr(
                settings,
                "ROBIOTEC_NOTIFICATION_SETTINGS_PATH",
                settings.BASE_DIR / "data" / "notification_settings.json",
            )
        )
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


class EmailSender:
    def send(self, config: dict[str, object]) -> list[str]:
        sender = str(config.get("sender_email") or "").strip()
        password = str(config.get("sender_password") or "").strip()
        host = str(config.get("smtp_host") or "").strip()
        port = int(config.get("smtp_port") or 587)
        recipients = _normalize_recipients(config.get("recipients"))
        if not sender:
            raise ValueError("Falta el correo emisor configurado.")
        if not password:
            raise ValueError("Falta la clave del correo emisor configurada.")
        if not host:
            raise ValueError("Falta el servidor SMTP configurado.")
        if not recipients:
            raise ValueError("No hay destinatarios configurados.")

        attachments = self._attachments(config.get("attachments"))
        sent: list[str] = []
        server = smtplib.SMTP(host, port)
        try:
            server.starttls()
            server.login(sender, password)
            for recipient in recipients:
                message = MIMEMultipart()
                message["From"] = sender
                message["To"] = recipient
                message["Subject"] = str(config.get("subject") or "")
                message.attach(MIMEText(str(config.get("message") or ""), "plain"))
                for part in attachments:
                    message.attach(part)
                server.sendmail(sender, recipient, message.as_string())
                sent.append(recipient)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return sent

    @staticmethod
    def _attachments(value: object) -> list[MIMEBase]:
        parts: list[MIMEBase] = []
        if not isinstance(value, list):
            return parts
        for item in value:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "adjunto.bin").strip() or "adjunto.bin"
            content = item.get("content", b"")
            payload = content.encode("utf-8") if isinstance(content, str) else bytes(content or b"")
            mime_type = str(item.get("mime_type") or "application/octet-stream")
            maintype, _separator, subtype = mime_type.partition("/")
            part = MIMEBase(maintype or "application", subtype or "octet-stream")
            part.set_payload(payload)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            parts.append(part)
        return parts


class _SimplePdf:
    def __init__(self, *, page_width: float = 595, page_height: float = 842, margin: float = 48) -> None:
        self.page_width = page_width
        self.page_height = page_height
        self.margin = margin
        self.pages: list[list[str]] = []
        self.commands: list[str] = []
        self.y = self._top_y()
        self.new_page()

    def new_page(self) -> None:
        if self.commands:
            self.pages.append(self.commands)
        self.commands = []
        self.y = self._top_y()

    def text(self, value: str, *, x: float = 48, size: int = 9, font: str = "F1", gap: float | None = None) -> None:
        line_height = gap if gap is not None else size + 4
        self._ensure_space(line_height)
        self.commands.append(f"BT /{font} {size} Tf {x:.1f} {self.y:.1f} Td ({_pdf_escape(value)}) Tj ET")
        self.y -= line_height

    def wrapped(self, value: str, *, x: float = 48, size: int = 9, width: int = 96, font: str = "F1") -> None:
        for line in textwrap.wrap(str(value or ""), width=width) or [""]:
            self.text(line, x=x, size=size, font=font)

    def rule(self) -> None:
        self._ensure_space(12)
        self.commands.append(f"0.65 w {self.margin:.1f} {self.y:.1f} m {self.page_width - self.margin:.1f} {self.y:.1f} l S")
        self.y -= 12

    def spacer(self, height: float = 8) -> None:
        self._ensure_space(height)
        self.y -= height

    def build(self) -> bytes:
        if self.commands:
            self.pages.append(self.commands)
            self.commands = []
        objects: list[bytes] = []
        pages_id = 2
        page_ids = [6 + index * 2 for index in range(len(self.pages))]
        content_ids = [page_id + 1 for page_id in page_ids]
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(self.pages)} >>".encode("latin-1"))
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        for page_id, content_id, commands in zip(page_ids, content_ids, self.pages):
            resources = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>"
            objects.append(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.page_width:.0f} {self.page_height:.0f}] /Resources {resources} /Contents {content_id} 0 R >>".encode("latin-1")
            )
            stream = "\n".join(commands).encode("latin-1", "replace")
            objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("ascii"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_at = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
        return bytes(output)

    def _ensure_space(self, height: float) -> None:
        if self.y - height < self.margin - 6:
            self.new_page()

    def _top_y(self) -> float:
        return self.page_height - self.margin - 4


def build_fleet_report_pdf(report: dict[str, object]) -> bytes:
    pdf = _SimplePdf(page_width=842, page_height=595)
    totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
    vehicles = report.get("vehicles") if isinstance(report.get("vehicles"), list) else []
    intervals = report.get("geofence_intervals") if isinstance(report.get("geofence_intervals"), list) else []

    pdf.text("Reporte diario de flota", size=18, font="F3")
    pdf.text(f"Fecha operativa: {report.get('date') or ''}", size=11, font="F3")
    pdf.text(f"Generado: {_fmt_datetime(report.get('generated_at'))}", size=9)
    pdf.rule()
    pdf.text(
        f"Km flota: {float(totals.get('total_km') or 0):.2f} | "
        f"Vehiculos activos: {totals.get('active_vehicles', 0)} / {totals.get('total_vehicles', 0)} | "
        f"Puntos GPS: {totals.get('total_points', 0)} | "
        f"Eventos geocerca: {totals.get('geofence_intervals', 0)}",
        size=10,
        font="F3",
    )
    pdf.spacer()
    pdf.text("Resumen de vehiculos", size=13, font="F3")
    widths = [16, 13, 14, 6, 18, 18, 9, 7]
    pdf.text(_table_line(["Vehiculo", "Marca", "Modelo", "A\u00f1o", "Chofer", "Tipo", "Km", "Puntos"], widths), font="F2", size=8)
    pdf.rule()
    for vehicle in vehicles:
        pdf.text(
            _table_line(
                [
                    vehicle.get("label") or vehicle.get("plate") or vehicle.get("vehicle_id"),
                    vehicle.get("brand") or "--",
                    vehicle.get("model") or "--",
                    vehicle.get("year") or "--",
                    vehicle.get("driver_name") or "--",
                    vehicle.get("vehicle_subtype_name") or "--",
                    f"{float(vehicle.get('total_km') or 0):.2f}",
                    int(vehicle.get("total_points") or 0),
                ],
                widths,
            ),
            font="F2",
            size=8,
        )

    pdf.spacer(12)
    pdf.text("Despiece de geocercas", size=13, font="F3")
    if intervals:
        widths = [16, 18, 10, 10, 9, 10]
        pdf.text(_table_line(["Vehiculo", "Geocerca", "Ingreso", "Salida", "Tiempo", "Estado"], widths), font="F2", size=8)
        pdf.rule()
        for interval in intervals:
            pdf.text(
                _table_line(
                    [
                        interval.get("vehicle_label"),
                        interval.get("geofence_name"),
                        _fmt_time(interval.get("entry_at")),
                        _fmt_geofence_exit(interval),
                        _fmt_minutes(interval.get("duration_minutes")),
                        interval.get("status"),
                    ],
                    widths,
                ),
                font="F2",
                size=8,
            )
    else:
        pdf.text("Sin permanencias registradas en geocercas para este dia.", size=9)

    pdf.new_page()
    pdf.text("Detalle por vehiculo", size=16, font="F3")
    pdf.rule()
    for vehicle in vehicles:
        pdf.text(str(vehicle.get("label") or vehicle.get("plate") or vehicle.get("vehicle_id")), size=12, font="F3")
        pdf.text(
            f"Placa: {vehicle.get('plate') or '--'} | Marca: {vehicle.get('brand') or '--'} | "
            f"Modelo: {vehicle.get('model') or '--'} | A\u00f1o: {vehicle.get('year') or '--'} | "
            f"Chofer: {vehicle.get('driver_name') or '--'} | Tipo: {vehicle.get('vehicle_subtype_name') or '--'}",
            size=9,
        )
        pdf.text(
            f"Km: {float(vehicle.get('total_km') or 0):.2f} | Ruta: "
            f"{_fmt_time(vehicle.get('start_at'))} {_fmt_coord(vehicle.get('start_lat'), vehicle.get('start_lon'))} -> "
            f"{_fmt_time(vehicle.get('end_at'))} {_fmt_coord(vehicle.get('end_lat'), vehicle.get('end_lon'))}",
            size=9,
        )
        vehicle_intervals = vehicle.get("geofence_intervals") if isinstance(vehicle.get("geofence_intervals"), list) else []
        if vehicle_intervals:
            pdf.text("Geocercas:", size=9, font="F3")
            for interval in vehicle_intervals:
                pdf.wrapped(
                    f"- {interval.get('geofence_name')}: ingreso {_fmt_time(interval.get('entry_at'))}, "
                    f"salida {_fmt_geofence_exit(interval)}, permanencia {_fmt_minutes(interval.get('duration_minutes'))}, "
                    f"estado {interval.get('status')}",
                    x=58,
                    size=8,
                    width=98,
                )
        else:
            pdf.text("Geocercas: sin permanencias registradas.", size=8, x=58)
        pdf.spacer(8)
    return pdf.build()


def _parse_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if text:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    return timezone.localdate() - timedelta(days=1)


def _parse_send_time(value: object) -> str:
    text = str(value or DEFAULT_SEND_TIME).strip()
    try:
        parsed = time.fromisoformat(text[:5])
    except ValueError:
        return DEFAULT_SEND_TIME
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def _time_from_text(value: str) -> time:
    hour, minute = [int(part) for part in _parse_send_time(value).split(":", 1)]
    return time(hour=hour, minute=minute)


def _normalize_recipients(value: object) -> list[str]:
    if isinstance(value, str):
        source = value.replace(",", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, list):
        source = value
    else:
        source = []
    seen: set[str] = set()
    recipients: list[str] = []
    for item in source:
        email = str(item or "").strip()
        key = email.lower()
        if "@" not in email or key in seen:
            continue
        seen.add(key)
        recipients.append(email)
    return recipients


def _local_bounds(report_date: date) -> tuple[datetime, datetime]:
    local_tz = timezone.get_current_timezone()
    start = datetime.combine(report_date, time.min, tzinfo=local_tz)
    return start, start + timedelta(days=1)


def _local_date(value: datetime) -> date:
    return timezone.localtime(value).date()


def _valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (abs(latitude) < 0.000001 and abs(longitude) < 0.000001)
    )


def _fleet_key(vehicle: Vehicle) -> str:
    raw = str(vehicle.plate or vehicle.name or vehicle.unique_code or vehicle.id).upper()
    match = re.search(r"([A-Z]{2,4})[ -]?([0-9]{3,5})", raw)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return re.sub(r"[^A-Z0-9]", "", raw) or str(vehicle.id)


def _vehicle_label(vehicle: Vehicle) -> str:
    raw = str(vehicle.plate or vehicle.name or vehicle.unique_code or vehicle.id).strip()
    match = re.search(r"([A-Z]{2,4})[ -]?([0-9]{3,5})", raw.upper())
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return raw


def _vehicle_subtype_label(value: object) -> str:
    key = str(value or "").strip().lower()
    return SUBTYPE_LABELS.get(key, key.replace("_", " ").title() if key else "Sin especificar")


def _geofence_interval_item(template: dict[str, object], entry_at: datetime, exit_at: datetime, status: str) -> dict[str, object]:
    minutes = max(0.0, (exit_at - entry_at).total_seconds() / 60)
    return {
        "vehicle_id": str(template.get("vehicle_id") or ""),
        "source_vehicle_id": str(template.get("source_vehicle_id") or ""),
        "vehicle_label": str(template.get("label") or template.get("plate") or template.get("vehicle_id") or ""),
        "plate": str(template.get("plate") or ""),
        "driver_name": str(template.get("driver_name") or ""),
        "vehicle_subtype": str(template.get("vehicle_subtype") or ""),
        "vehicle_subtype_name": _vehicle_subtype_label(template.get("vehicle_subtype")),
        "geofence_id": str(template.get("geofence_id") or ""),
        "geofence_name": str(template.get("geofence_name") or "Geocerca"),
        "entry_at": entry_at.isoformat(),
        "exit_at": exit_at.isoformat(),
        "duration_minutes": round(minutes, 1),
        "status": status,
    }


def _extend_last_geofence_interval(interval: dict[str, object], exit_at: datetime) -> None:
    entry_at = _datetime_from_iso(interval.get("entry_at"))
    current_exit = _datetime_from_iso(interval.get("exit_at"))
    if not entry_at or (current_exit and exit_at <= current_exit) or exit_at <= entry_at:
        return
    interval["exit_at"] = exit_at.isoformat()
    interval["duration_minutes"] = round((exit_at - entry_at).total_seconds() / 60, 1)
    interval["status"] = "salio"


def _merge_interval_union(
    raw_intervals: list[tuple[datetime, datetime, bool, dict[str, object]]],
) -> list[tuple[datetime, datetime, bool, dict[str, object]]]:
    ordered = sorted(raw_intervals, key=lambda item: item[0])
    merged: list[list[object]] = []
    for start, end, is_open, template in ordered:
        if merged and start <= merged[-1][1]:
            if end >= merged[-1][1]:
                merged[-1][1] = end
                merged[-1][2] = is_open
                merged[-1][3] = template
        else:
            merged.append([start, end, is_open, template])
    return [(start, end, is_open, template) for start, end, is_open, template in merged]


def _resolve_vehicle_geofence_overlaps(intervals: list[dict[str, object]]) -> list[dict[str, object]]:
    by_vehicle: dict[str, list[dict[str, object]]] = defaultdict(list)
    for interval in intervals:
        by_vehicle[str(interval.get("vehicle_id") or "")].append(interval)

    resolved: list[dict[str, object]] = []
    for vehicle_intervals in by_vehicle.values():
        selected: list[dict[str, object]] = []
        for interval in sorted(vehicle_intervals, key=_geofence_interval_time_key):
            start = _datetime_from_iso(interval.get("entry_at"))
            end = _datetime_from_iso(interval.get("exit_at"))
            if not start or not end:
                selected.append(interval)
                continue
            previous = selected[-1] if selected else None
            previous_end = _datetime_from_iso(previous.get("exit_at")) if previous else None
            if previous_end and start < previous_end:
                continue
            selected.append(interval)
        resolved.extend(selected)
    return resolved


def _geofence_interval_time_key(item: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(item.get("entry_at") or ""),
        str(item.get("exit_at") or ""),
        str(item.get("vehicle_label") or ""),
        str(item.get("geofence_name") or ""),
    )


def _geofence_interval_sort_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("entry_at") or ""),
        str(item.get("vehicle_label") or ""),
        str(item.get("geofence_name") or ""),
    )


def _datetime_from_iso(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime_timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime_timezone.utc)


def _fmt_datetime(value: object) -> str:
    if not value:
        return "--"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)[:19]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime_timezone.utc)
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M")


def _fmt_time(value: object) -> str:
    text = _fmt_datetime(value)
    return text[-5:] if text and text != "--" else "--"


def _fmt_minutes(value: object) -> str:
    total = max(0, int(round(float(value or 0))))
    hours, minutes = divmod(total, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _fmt_geofence_exit(interval: dict[str, object]) -> str:
    if str(interval.get("status") or "").lower() == "permanece":
        return "permanece"
    return _fmt_time(interval.get("exit_at"))


def _fmt_coord(lat: object, lon: object) -> str:
    try:
        return f"{float(lat):.6f}, {float(lon):.6f}"
    except (TypeError, ValueError):
        return "--"


def _pdf_escape(value: object) -> str:
    text = str(value or "").encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _fit(value: object, width: int) -> str:
    text = str(value or "")
    return text.ljust(width) if len(text) <= width else (text[: max(0, width - 3)] + "...").ljust(width)


def _table_line(values: list[object], widths: list[int]) -> str:
    return "  ".join(_fit(value, width) for value, width in zip(values, widths))


def _iso(value: object) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ""
