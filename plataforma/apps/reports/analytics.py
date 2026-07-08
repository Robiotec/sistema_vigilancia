from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.utils import timezone

from apps.alerts.models import CameraEventHistory
from apps.devices.models import Camera

MAX_REPORT_EVENTS = 50_000


@dataclass(frozen=True)
class ReportRange:
    start_day: date
    end_day: date
    start_at: datetime
    end_at: datetime


class DetectionReportService:
    def cameras(self) -> list[dict[str, object]]:
        latest_by_id: dict[str, CameraEventHistory] = {}
        rows = (
            CameraEventHistory.objects.exclude(camera_id__isnull=True)
            .exclude(camera_id="")
            .order_by("camera_id", "-detected_at", "-created_at")
        )
        for row in rows:
            if row.camera_id not in latest_by_id:
                latest_by_id[row.camera_id] = row
        camera_names = {
            camera.unique_code: camera.name
            for camera in Camera.objects.filter(unique_code__in=latest_by_id.keys())
            if camera.unique_code
        }
        return sorted(
            [
                {
                    "camera_id": camera_id,
                    "camera_name": camera_names.get(camera_id) or event.camera_name or camera_id,
                }
                for camera_id, event in latest_by_id.items()
            ],
            key=lambda item: str(item["camera_name"]).lower(),
        )

    def overview(self, *, from_date: str, to_date: str, camera_id: str = "") -> dict[str, object]:
        events = self._events(from_date=from_date, to_date=to_date, camera_id=camera_id)
        person_events = [event for event in events if event.event_type == "person" and _clean(event.person_id)]
        plate_events = [event for event in events if event.event_type == "plate" and _clean(event.plate)]
        return {
            "person_events": len(person_events),
            "people_detected": len({_clean(event.person_id) for event in person_events}),
            "plate_events": len(plate_events),
            "plates_detected": len({_clean(event.plate).upper() for event in plate_events}),
            "active_cameras": len({_clean(event.camera_id) for event in events if _clean(event.camera_id)}),
            "first_seen": _dt(min((event.detected_at for event in events), default=None)),
            "last_seen": _dt(max((event.detected_at for event in events), default=None)),
        }

    def personnel_daily(
        self,
        *,
        from_date: str,
        to_date: str,
        gap_minutes: int = 15,
        camera_id: str = "",
        person_id: str = "",
    ) -> list[dict[str, object]]:
        events = self._person_events(from_date=from_date, to_date=to_date, camera_id=camera_id, person_id=person_id)
        return self._daily_rows(events, self._gap_seconds(gap_minutes))

    def personnel_sessions(
        self,
        *,
        person_id: str,
        from_date: str,
        to_date: str,
        work_date: str = "",
        gap_minutes: int = 15,
        camera_id: str = "",
    ) -> list[dict[str, object]]:
        events = self._person_events(from_date=from_date, to_date=to_date, camera_id=camera_id, person_id=person_id)
        target_day = _parse_day(work_date, "work_date") if work_date else None
        grouped: dict[tuple[str, date], list[CameraEventHistory]] = defaultdict(list)
        for event in events:
            local_day = _local_day(event.detected_at)
            if target_day and local_day != target_day:
                continue
            grouped[(_clean(event.person_id), local_day)].append(event)
        rows: list[dict[str, object]] = []
        gap_seconds = self._gap_seconds(gap_minutes)
        for (pid, local_day), items in grouped.items():
            sessions = self._sessions(items, gap_seconds)
            previous_exit = None
            for index, session in enumerate(sessions, start=1):
                entry = session[0].detected_at
                exit_at = session[-1].detected_at
                rows.append(
                    {
                        "person_id": pid,
                        "person_name": self._person_name(session),
                        "work_date": local_day.isoformat(),
                        "session_no": index,
                        "entry_at": _dt(entry),
                        "exit_at": _dt(exit_at),
                        "minutes_inside_session": round(max((exit_at - entry).total_seconds(), 0) / 60, 1),
                        "minutes_since_previous_exit": (
                            round(max((entry - previous_exit).total_seconds(), 0) / 60, 1) if previous_exit else None
                        ),
                        "detections": len(session),
                        "cameras": self._camera_names(session),
                    }
                )
                previous_exit = exit_at
        return sorted(rows, key=lambda row: (str(row["work_date"]), int(row["session_no"])), reverse=True)

    def personnel_monthly(self, *, year: int, month: int, gap_minutes: int = 15, camera_id: str = "") -> list[dict[str, object]]:
        start_day, end_day = _month_days(year, month)
        daily_rows = self.personnel_daily(
            from_date=start_day.isoformat(),
            to_date=(end_day - timedelta(days=1)).isoformat(),
            gap_minutes=gap_minutes,
            camera_id=camera_id,
        )
        by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in daily_rows:
            by_person[str(row["person_id"])].append(row)
        rows = []
        for person_id, items in by_person.items():
            total_hours = round(sum(float(item.get("hours") or 0) for item in items), 2)
            rows.append(
                {
                    "person_id": person_id,
                    "person_name": next((str(item.get("person_name") or "") for item in items if item.get("person_name")), ""),
                    "days_present": len(items),
                    "total_hours": total_hours,
                    "avg_hours_day": round(total_hours / len(items), 2) if items else 0,
                    "sessions": sum(int(item.get("sessions") or 0) for item in items),
                    "reentries": sum(int(item.get("reentries") or 0) for item in items),
                    "detections": sum(int(item.get("detections") or 0) for item in items),
                    "first_seen": min((str(item.get("first_seen") or "") for item in items if item.get("first_seen")), default=""),
                    "last_seen": max((str(item.get("last_seen") or "") for item in items if item.get("last_seen")), default=""),
                }
            )
        return sorted(rows, key=lambda row: (int(row["days_present"]), float(row["total_hours"])), reverse=True)

    def plates(self, *, from_date: str, to_date: str, camera_id: str = "") -> list[dict[str, object]]:
        events = [
            event
            for event in self._events(from_date=from_date, to_date=to_date, camera_id=camera_id)
            if event.event_type == "plate" and _clean(event.plate)
        ]
        grouped: dict[tuple[str, str], list[CameraEventHistory]] = defaultdict(list)
        for event in events:
            grouped[(_clean(event.plate).upper(), _clean(event.camera_id))].append(event)
        rows = []
        for (plate, cam_id), items in grouped.items():
            rows.append(
                {
                    "plate": plate,
                    "camera_id": cam_id,
                    "camera_name": self._camera_names(items),
                    "detections": len(items),
                    "days_detected": len({_local_day(item.detected_at) for item in items}),
                    "first_seen": _dt(min(item.detected_at for item in items)),
                    "last_seen": _dt(max(item.detected_at for item in items)),
                }
            )
        return sorted(rows, key=lambda row: (int(row["detections"]), str(row["last_seen"])), reverse=True)[:500]

    def _events(self, *, from_date: str, to_date: str, camera_id: str = "") -> list[CameraEventHistory]:
        report_range = _range(from_date, to_date)
        queryset = CameraEventHistory.objects.filter(
            detected_at__gte=report_range.start_at,
            detected_at__lt=report_range.end_at,
        ).order_by("detected_at", "id")
        if camera_id:
            queryset = queryset.filter(camera_id=camera_id)
        return list(queryset[:MAX_REPORT_EVENTS])

    def _person_events(
        self,
        *,
        from_date: str,
        to_date: str,
        camera_id: str = "",
        person_id: str = "",
    ) -> list[CameraEventHistory]:
        events = [
            event
            for event in self._events(from_date=from_date, to_date=to_date, camera_id=camera_id)
            if event.event_type == "person" and _clean(event.person_id)
        ]
        if person_id:
            target = _clean(person_id)
            events = [event for event in events if _clean(event.person_id) == target]
        return events

    def _daily_rows(self, events: list[CameraEventHistory], gap_seconds: int) -> list[dict[str, object]]:
        grouped: dict[tuple[str, date], list[CameraEventHistory]] = defaultdict(list)
        for event in events:
            grouped[(_clean(event.person_id), _local_day(event.detected_at))].append(event)
        rows = []
        for (person_id, local_day), items in grouped.items():
            sessions = self._sessions(items, gap_seconds)
            first = min(item.detected_at for item in items)
            last = max(item.detected_at for item in items)
            rows.append(
                {
                    "person_id": person_id,
                    "person_name": self._person_name(items),
                    "work_date": local_day.isoformat(),
                    "first_seen": _dt(first),
                    "last_seen": _dt(last),
                    "hours": round(max((last - first).total_seconds(), 0) / 3600, 2),
                    "sessions": len(sessions),
                    "reentries": max(len(sessions) - 1, 0),
                    "detections": len(items),
                    "cameras": self._camera_names(items),
                }
            )
        return sorted(rows, key=lambda row: (str(row["work_date"]), str(row["first_seen"]), str(row["person_id"])), reverse=True)

    @staticmethod
    def _sessions(events: list[CameraEventHistory], gap_seconds: int) -> list[list[CameraEventHistory]]:
        sessions: list[list[CameraEventHistory]] = []
        for event in sorted(events, key=lambda item: item.detected_at):
            if not sessions:
                sessions.append([event])
                continue
            previous = sessions[-1][-1]
            if (event.detected_at - previous.detected_at).total_seconds() > gap_seconds:
                sessions.append([event])
            else:
                sessions[-1].append(event)
        return sessions

    @staticmethod
    def _gap_seconds(gap_minutes: int) -> int:
        try:
            value = int(gap_minutes)
        except (TypeError, ValueError):
            value = 15
        return max(1, min(value, 720)) * 60

    @staticmethod
    def _person_name(events: list[CameraEventHistory]) -> str:
        return next((_clean(event.person_name) for event in events if _clean(event.person_name)), "")

    @staticmethod
    def _camera_names(events: list[CameraEventHistory]) -> str:
        names = []
        for event in events:
            name = _clean(event.camera_name) or _clean(event.camera_id)
            if name and name not in names:
                names.append(name)
        return ", ".join(names)


def _range(from_date: str, to_date: str) -> ReportRange:
    start_day = _parse_day(from_date, "from_date")
    end_day = _parse_day(to_date, "to_date")
    if end_day < start_day:
        raise ValueError("to_date no puede ser menor que from_date")
    current_tz = timezone.get_current_timezone()
    start_at = timezone.make_aware(datetime.combine(start_day, time.min), current_tz)
    end_at = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), current_tz)
    return ReportRange(start_day=start_day, end_day=end_day, start_at=start_at, end_at=end_at)


def _month_days(year: int, month: int) -> tuple[date, date]:
    if year < 2000 or year > 2100:
        raise ValueError("year fuera de rango")
    if month < 1 or month > 12:
        raise ValueError("month debe estar entre 1 y 12")
    start = date(year, month, 1)
    if month == 12:
        return start, date(year + 1, 1, 1)
    return start, date(year, month + 1, 1)


def _parse_day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{field} debe tener formato YYYY-MM-DD") from exc


def _local_day(value: datetime) -> date:
    return timezone.localtime(value).date()


def _dt(value: datetime | None) -> str:
    return timezone.localtime(value).isoformat() if value else ""


def _clean(value: object) -> str:
    return str(value or "").strip()
