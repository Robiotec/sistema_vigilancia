"""Estadísticas y reportes de detecciones de personas y placas."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from back.app.context import require_authenticated_request
from back.app.services.db_pool import fetch_all

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(require_authenticated_request)])

EC_TZ = timezone(timedelta(hours=-5))
LOCAL_DAY_SQL = "(detected_at AT TIME ZONE 'America/Guayaquil')::date"


def _parse_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(str(raw or "").strip())
    except ValueError as exc:
        raise ValueError(f"{field} debe tener formato YYYY-MM-DD") from exc


def _parse_range(from_date: str, to_date: str) -> tuple[datetime, datetime]:
    start_day = _parse_date(from_date, "from_date")
    end_day = _parse_date(to_date, "to_date")
    if end_day < start_day:
        raise ValueError("to_date no puede ser menor que from_date")
    from_ts = datetime.combine(start_day, datetime.min.time(), tzinfo=EC_TZ)
    to_ts = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=EC_TZ)
    return from_ts, to_ts


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    if year < 2000 or year > 2100:
        raise ValueError("year fuera de rango")
    if month < 1 or month > 12:
        raise ValueError("month debe estar entre 1 y 12")
    from_ts = datetime(year, month, 1, tzinfo=EC_TZ)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    to_ts = datetime(next_year, next_month, 1, tzinfo=EC_TZ)
    return from_ts, to_ts


def _gap_seconds(gap_minutes: int) -> int:
    try:
        value = int(gap_minutes)
    except (TypeError, ValueError):
        value = 15
    return max(1, min(value, 720)) * 60


def _row(row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, date):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = float(value)
        else:
            out[key] = value
    return out


def _fmt_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(EC_TZ).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=EC_TZ)
            return parsed.astimezone(EC_TZ).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
    return str(value)


def _csv_response(filename: str, rows: list[list[Any]]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter(["\ufeff" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _error(exc: Exception, status_code: int = 500) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=status_code)


_CAMERAS_SQL = """
WITH event_cameras AS (
    SELECT camera_id, camera_name
    FROM (
        SELECT DISTINCT ON (camera_id)
            camera_id,
            COALESCE(NULLIF(camera_name, ''), camera_id) AS camera_name
        FROM camera_event_history
        WHERE camera_id IS NOT NULL AND camera_id <> ''
        ORDER BY camera_id, detected_at DESC NULLS LAST, created_at DESC NULLS LAST
    ) latest
)
SELECT
    ec.camera_id,
    COALESCE(NULLIF(c.name, ''), ec.camera_name, ec.camera_id) AS camera_name
FROM event_cameras ec
LEFT JOIN cameras c ON c.unique_code = ec.camera_id AND c.deleted_at IS NULL
ORDER BY camera_name
"""

_LEGACY_CAMERAS_SQL = """
SELECT camera_id, camera_name
FROM (
    SELECT DISTINCT ON (camera_id)
        camera_id,
        COALESCE(NULLIF(camera_name, ''), camera_id) AS camera_name
    FROM camera_event_history
    WHERE camera_id IS NOT NULL AND camera_id <> ''
    ORDER BY camera_id, detected_at DESC NULLS LAST, created_at DESC NULLS LAST
) c
ORDER BY camera_name
"""

_OVERVIEW_SQL = f"""
SELECT
    COUNT(*) FILTER (WHERE event_type = 'person') AS person_events,
    COUNT(DISTINCT btrim(person_id)) FILTER (
        WHERE event_type = 'person' AND person_id IS NOT NULL AND btrim(person_id) <> ''
    ) AS people_detected,
    COUNT(*) FILTER (WHERE event_type = 'plate') AS plate_events,
    COUNT(DISTINCT upper(btrim(plate))) FILTER (
        WHERE event_type = 'plate' AND plate IS NOT NULL AND btrim(plate) <> ''
    ) AS plates_detected,
    COUNT(DISTINCT camera_id) FILTER (
        WHERE camera_id IS NOT NULL AND camera_id <> ''
    ) AS active_cameras,
    MIN(detected_at) AS first_seen,
    MAX(detected_at) AS last_seen
FROM camera_event_history
WHERE detected_at >= %(from_ts)s
  AND detected_at < %(to_ts)s
  AND event_type IN ('person', 'plate')
  AND (%(camera_id)s = '' OR camera_id = %(camera_id)s)
"""

_PERSON_EVENT_FILTER = """
WHERE event_type = 'person'
  AND person_id IS NOT NULL AND btrim(person_id) <> ''
  AND detected_at >= %(from_ts)s
  AND detected_at < %(to_ts)s
  AND (%(camera_id)s = '' OR camera_id = %(camera_id)s)
"""

_DAILY_SQL = f"""
WITH ordered AS (
    SELECT
        btrim(person_id) AS person_id,
        NULLIF(btrim(person_name), '') AS person_name,
        camera_id,
        COALESCE(NULLIF(camera_name, ''), camera_id) AS camera_name,
        detected_at,
        {LOCAL_DAY_SQL} AS work_date,
        LAG(detected_at) OVER (
            PARTITION BY btrim(person_id), {LOCAL_DAY_SQL}
            ORDER BY detected_at
        ) AS prev_ts
    FROM camera_event_history
    {_PERSON_EVENT_FILTER}
),
marked AS (
    SELECT
        *,
        CASE
            WHEN prev_ts IS NULL THEN 1
            WHEN EXTRACT(EPOCH FROM (detected_at - prev_ts)) > %(gap_secs)s THEN 1
            ELSE 0
        END AS starts_session
    FROM ordered
),
sessionized AS (
    SELECT
        *,
        SUM(starts_session) OVER (
            PARTITION BY person_id, work_date
            ORDER BY detected_at
            ROWS UNBOUNDED PRECEDING
        ) AS session_no
    FROM marked
),
daily AS (
    SELECT
        person_id,
        MAX(person_name) FILTER (WHERE person_name IS NOT NULL) AS person_name,
        work_date,
        MIN(detected_at) AS first_seen,
        MAX(detected_at) AS last_seen,
        COUNT(DISTINCT session_no) AS sessions,
        GREATEST(COUNT(DISTINCT session_no) - 1, 0) AS reentries,
        COUNT(*) AS detections,
        array_to_string(array_agg(DISTINCT camera_name), ', ') AS cameras
    FROM sessionized
    GROUP BY person_id, work_date
)
SELECT
    person_id,
    person_name,
    work_date,
    first_seen,
    last_seen,
    ROUND((EXTRACT(EPOCH FROM (last_seen - first_seen)) / 3600.0)::numeric, 2) AS hours,
    sessions,
    reentries,
    detections,
    cameras
FROM daily
ORDER BY work_date DESC, first_seen ASC, person_id
"""

_INDIVIDUAL_SQL = _DAILY_SQL.replace(
    "AND (%(camera_id)s = '' OR camera_id = %(camera_id)s)",
    "AND (%(camera_id)s = '' OR camera_id = %(camera_id)s)\n  AND btrim(person_id) = btrim(%(person_id)s)",
)

_MONTHLY_SQL = f"""
WITH ordered AS (
    SELECT
        btrim(person_id) AS person_id,
        NULLIF(btrim(person_name), '') AS person_name,
        detected_at,
        {LOCAL_DAY_SQL} AS work_date,
        LAG(detected_at) OVER (
            PARTITION BY btrim(person_id), {LOCAL_DAY_SQL}
            ORDER BY detected_at
        ) AS prev_ts
    FROM camera_event_history
    {_PERSON_EVENT_FILTER}
),
marked AS (
    SELECT
        *,
        CASE
            WHEN prev_ts IS NULL THEN 1
            WHEN EXTRACT(EPOCH FROM (detected_at - prev_ts)) > %(gap_secs)s THEN 1
            ELSE 0
        END AS starts_session
    FROM ordered
),
sessionized AS (
    SELECT
        *,
        SUM(starts_session) OVER (
            PARTITION BY person_id, work_date
            ORDER BY detected_at
            ROWS UNBOUNDED PRECEDING
        ) AS session_no
    FROM marked
),
daily AS (
    SELECT
        person_id,
        MAX(person_name) FILTER (WHERE person_name IS NOT NULL) AS person_name,
        work_date,
        MIN(detected_at) AS first_seen,
        MAX(detected_at) AS last_seen,
        COUNT(DISTINCT session_no) AS sessions,
        GREATEST(COUNT(DISTINCT session_no) - 1, 0) AS reentries,
        COUNT(*) AS detections
    FROM sessionized
    GROUP BY person_id, work_date
)
SELECT
    person_id,
    MAX(person_name) AS person_name,
    COUNT(*) AS days_present,
    ROUND(SUM(EXTRACT(EPOCH FROM (last_seen - first_seen)) / 3600.0)::numeric, 2) AS total_hours,
    ROUND((SUM(EXTRACT(EPOCH FROM (last_seen - first_seen))) / COUNT(*) / 3600.0)::numeric, 2) AS avg_hours_day,
    SUM(sessions)::int AS sessions,
    SUM(reentries)::int AS reentries,
    SUM(detections)::int AS detections,
    MIN(first_seen) AS first_seen,
    MAX(last_seen) AS last_seen
FROM daily
GROUP BY person_id
ORDER BY days_present DESC, total_hours DESC, person_id
"""

_SESSIONS_SQL = f"""
WITH ordered AS (
    SELECT
        id,
        btrim(person_id) AS person_id,
        NULLIF(btrim(person_name), '') AS person_name,
        camera_id,
        COALESCE(NULLIF(camera_name, ''), camera_id) AS camera_name,
        detected_at,
        {LOCAL_DAY_SQL} AS work_date,
        LAG(detected_at) OVER (
            PARTITION BY btrim(person_id), {LOCAL_DAY_SQL}
            ORDER BY detected_at
        ) AS prev_ts
    FROM camera_event_history
    {_PERSON_EVENT_FILTER}
      AND btrim(person_id) = btrim(%(person_id)s)
      AND (NULLIF(%(work_date)s, '') IS NULL OR {LOCAL_DAY_SQL} = NULLIF(%(work_date)s, '')::date)
),
marked AS (
    SELECT
        *,
        CASE
            WHEN prev_ts IS NULL THEN 1
            WHEN EXTRACT(EPOCH FROM (detected_at - prev_ts)) > %(gap_secs)s THEN 1
            ELSE 0
        END AS starts_session
    FROM ordered
),
sessionized AS (
    SELECT
        *,
        SUM(starts_session) OVER (
            PARTITION BY person_id, work_date
            ORDER BY detected_at
            ROWS UNBOUNDED PRECEDING
        ) AS session_no
    FROM marked
),
sessions AS (
    SELECT
        person_id,
        MAX(person_name) FILTER (WHERE person_name IS NOT NULL) AS person_name,
        work_date,
        session_no,
        MIN(detected_at) AS entry_at,
        MAX(detected_at) AS exit_at,
        COUNT(*) AS detections,
        array_to_string(array_agg(DISTINCT camera_name), ', ') AS cameras
    FROM sessionized
    GROUP BY person_id, work_date, session_no
),
with_gaps AS (
    SELECT
        *,
        LAG(exit_at) OVER (
            PARTITION BY person_id, work_date
            ORDER BY session_no
        ) AS previous_exit_at
    FROM sessions
)
SELECT
    person_id,
    person_name,
    work_date,
    session_no,
    entry_at,
    exit_at,
    ROUND((EXTRACT(EPOCH FROM (exit_at - entry_at)) / 60.0)::numeric, 1) AS minutes_inside_session,
    ROUND((EXTRACT(EPOCH FROM (entry_at - previous_exit_at)) / 60.0)::numeric, 1) AS minutes_since_previous_exit,
    detections,
    cameras
FROM with_gaps
ORDER BY work_date DESC, session_no ASC
"""

_PLATES_SQL = f"""
SELECT
    upper(btrim(plate)) AS plate,
    camera_id,
    COALESCE(NULLIF(camera_name, ''), camera_id) AS camera_name,
    COUNT(*) AS detections,
    MIN(detected_at) AS first_seen,
    MAX(detected_at) AS last_seen,
    COUNT(DISTINCT {LOCAL_DAY_SQL}) AS days_detected
FROM camera_event_history
WHERE event_type = 'plate'
  AND plate IS NOT NULL AND btrim(plate) <> ''
  AND detected_at >= %(from_ts)s
  AND detected_at < %(to_ts)s
  AND (%(camera_id)s = '' OR camera_id = %(camera_id)s)
GROUP BY upper(btrim(plate)), camera_id, COALESCE(NULLIF(camera_name, ''), camera_id)
ORDER BY detections DESC, last_seen DESC
LIMIT 500
"""


@router.get("/cameras")
def report_cameras():
    try:
        return [_row(row) for row in fetch_all(_CAMERAS_SQL)]
    except Exception as exc:
        try:
            return [_row(row) for row in fetch_all(_LEGACY_CAMERAS_SQL)]
        except Exception:
            return _error(exc)


@router.get("/overview")
def reports_overview(from_date: str = "", to_date: str = "", camera_id: str = ""):
    if not from_date or not to_date:
        return _error(ValueError("from_date y to_date requeridos"), 400)
    try:
        from_ts, to_ts = _parse_range(from_date, to_date)
        rows = fetch_all(_OVERVIEW_SQL, {"from_ts": from_ts, "to_ts": to_ts, "camera_id": camera_id or ""})
        return _row(rows[0]) if rows else {}
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/personnel/daily")
def personnel_daily(from_date: str = "", to_date: str = "", gap_minutes: int = 15, camera_id: str = ""):
    if not from_date or not to_date:
        return _error(ValueError("from_date y to_date requeridos"), 400)
    try:
        from_ts, to_ts = _parse_range(from_date, to_date)
        params = {"from_ts": from_ts, "to_ts": to_ts, "gap_secs": _gap_seconds(gap_minutes), "camera_id": camera_id or ""}
        return [_row(row) for row in fetch_all(_DAILY_SQL, params)]
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/personnel/daily/export")
def personnel_daily_export(from_date: str = "", to_date: str = "", gap_minutes: int = 15, camera_id: str = ""):
    response = personnel_daily(from_date=from_date, to_date=to_date, gap_minutes=gap_minutes, camera_id=camera_id)
    if isinstance(response, JSONResponse):
        return response
    csv_rows: list[list[Any]] = [["Cedula", "Nombre", "Fecha", "Entrada", "Salida", "Horas", "Sesiones", "Reingresos", "Detecciones", "Camaras"]]
    for row in response:
        csv_rows.append([
            row.get("person_id", ""),
            row.get("person_name", ""),
            row.get("work_date", ""),
            _fmt_dt(row.get("first_seen")),
            _fmt_dt(row.get("last_seen")),
            row.get("hours", 0),
            row.get("sessions", 0),
            row.get("reentries", 0),
            row.get("detections", 0),
            row.get("cameras", ""),
        ])
    return _csv_response(f"personal_diario_{from_date}_{to_date}.csv", csv_rows)


@router.get("/personnel/individual")
def personnel_individual(
    person_id: str = "",
    from_date: str = "",
    to_date: str = "",
    gap_minutes: int = 15,
    camera_id: str = "",
):
    if not person_id or not from_date or not to_date:
        return _error(ValueError("person_id, from_date y to_date requeridos"), 400)
    try:
        from_ts, to_ts = _parse_range(from_date, to_date)
        params = {
            "person_id": person_id.strip(),
            "from_ts": from_ts,
            "to_ts": to_ts,
            "gap_secs": _gap_seconds(gap_minutes),
            "camera_id": camera_id or "",
        }
        return [_row(row) for row in fetch_all(_INDIVIDUAL_SQL, params)]
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/personnel/sessions")
def personnel_sessions(
    person_id: str = "",
    from_date: str = "",
    to_date: str = "",
    work_date: str = "",
    gap_minutes: int = 15,
    camera_id: str = "",
):
    if not person_id or not from_date or not to_date:
        return _error(ValueError("person_id, from_date y to_date requeridos"), 400)
    try:
        from_ts, to_ts = _parse_range(from_date, to_date)
        if work_date:
            _parse_date(work_date, "work_date")
        params = {
            "person_id": person_id.strip(),
            "from_ts": from_ts,
            "to_ts": to_ts,
            "work_date": work_date.strip(),
            "gap_secs": _gap_seconds(gap_minutes),
            "camera_id": camera_id or "",
        }
        return [_row(row) for row in fetch_all(_SESSIONS_SQL, params)]
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/personnel/sessions/export")
def personnel_sessions_export(
    person_id: str = "",
    from_date: str = "",
    to_date: str = "",
    work_date: str = "",
    gap_minutes: int = 15,
    camera_id: str = "",
):
    response = personnel_sessions(
        person_id=person_id,
        from_date=from_date,
        to_date=to_date,
        work_date=work_date,
        gap_minutes=gap_minutes,
        camera_id=camera_id,
    )
    if isinstance(response, JSONResponse):
        return response
    csv_rows: list[list[Any]] = [["Cedula", "Nombre", "Fecha", "Sesion", "Entrada", "Salida estimada", "Minutos sesion", "Minutos desde salida anterior", "Detecciones", "Camaras"]]
    for row in response:
        csv_rows.append([
            row.get("person_id", ""),
            row.get("person_name", ""),
            row.get("work_date", ""),
            row.get("session_no", ""),
            _fmt_dt(row.get("entry_at")),
            _fmt_dt(row.get("exit_at")),
            row.get("minutes_inside_session", ""),
            row.get("minutes_since_previous_exit", ""),
            row.get("detections", 0),
            row.get("cameras", ""),
        ])
    suffix = work_date or f"{from_date}_{to_date}"
    return _csv_response(f"personal_sesiones_{person_id}_{suffix}.csv", csv_rows)


@router.get("/personnel/monthly")
def personnel_monthly(year: int = 0, month: int = 0, gap_minutes: int = 15, camera_id: str = ""):
    if not year or not month:
        return _error(ValueError("year y month requeridos"), 400)
    try:
        from_ts, to_ts = _month_range(year, month)
        params = {"from_ts": from_ts, "to_ts": to_ts, "gap_secs": _gap_seconds(gap_minutes), "camera_id": camera_id or ""}
        return [_row(row) for row in fetch_all(_MONTHLY_SQL, params)]
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/personnel/monthly/export")
def personnel_monthly_export(year: int = 0, month: int = 0, gap_minutes: int = 15, camera_id: str = ""):
    response = personnel_monthly(year=year, month=month, gap_minutes=gap_minutes, camera_id=camera_id)
    if isinstance(response, JSONResponse):
        return response
    csv_rows: list[list[Any]] = [["Cedula", "Nombre", "Dias presentes", "Horas totales", "Promedio h/dia", "Sesiones", "Reingresos", "Detecciones", "Primera deteccion", "Ultima deteccion"]]
    for row in response:
        csv_rows.append([
            row.get("person_id", ""),
            row.get("person_name", ""),
            row.get("days_present", 0),
            row.get("total_hours", 0),
            row.get("avg_hours_day", 0),
            row.get("sessions", 0),
            row.get("reentries", 0),
            row.get("detections", 0),
            _fmt_dt(row.get("first_seen")),
            _fmt_dt(row.get("last_seen")),
        ])
    return _csv_response(f"personal_mensual_{year}_{month:02d}.csv", csv_rows)


@router.get("/plates/stats")
def plates_stats(from_date: str = "", to_date: str = "", camera_id: str = ""):
    if not from_date or not to_date:
        return _error(ValueError("from_date y to_date requeridos"), 400)
    try:
        from_ts, to_ts = _parse_range(from_date, to_date)
        rows = fetch_all(_PLATES_SQL, {"from_ts": from_ts, "to_ts": to_ts, "camera_id": camera_id or ""})
        return [_row(row) for row in rows]
    except ValueError as exc:
        return _error(exc, 400)
    except Exception as exc:
        return _error(exc)


@router.get("/plates/export")
def plates_export(from_date: str = "", to_date: str = "", camera_id: str = ""):
    response = plates_stats(from_date=from_date, to_date=to_date, camera_id=camera_id)
    if isinstance(response, JSONResponse):
        return response
    csv_rows: list[list[Any]] = [["Placa", "Camara", "Detecciones", "Primera deteccion", "Ultima deteccion", "Dias detectada"]]
    for row in response:
        csv_rows.append([
            row.get("plate", ""),
            row.get("camera_name", ""),
            row.get("detections", 0),
            _fmt_dt(row.get("first_seen")),
            _fmt_dt(row.get("last_seen")),
            row.get("days_detected", 0),
        ])
    return _csv_response(f"placas_{from_date}_{to_date}.csv", csv_rows)
