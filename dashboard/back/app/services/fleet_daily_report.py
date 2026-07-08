from __future__ import annotations

import json
import logging
import threading
import textwrap
import time
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any

from back.app.services.db_pool import execute, fetch_all
from back.app.services.notification_settings import (
    load_email_recipients_from_db,
    load_notification_settings,
)
from back.app.services.send_mail import send_email

LOG = logging.getLogger(__name__)

ECUADOR_TZ = timezone(timedelta(hours=-5))
MAX_SEGMENT_GAP_SECONDS = 30 * 60
MAX_SEGMENT_DISTANCE_KM = 8.0
MAX_REASONABLE_SPEED_KMH = 180.0
DEFAULT_SEND_TIME = "07:00"

FLEET_REPORT_SETTINGS_SQL = """
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

SUBTYPE_LABELS = {
    "volqueta": "Volqueta",
    "camion": "Camión",
    "camioneta": "Camioneta",
    "retroexcavadora": "Retroexcavadora",
    "otra": "Otra",
    "sin_especificar": "Sin especificar",
}


def _now_local() -> datetime:
    return datetime.now(ECUADOR_TZ)


def _iso_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _parse_date(value: Any, default: date | None = None) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if text:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    return default or (_now_local().date() - timedelta(days=1))


def _parse_send_time(value: Any) -> str:
    text = str(value or DEFAULT_SEND_TIME).strip()
    try:
        parsed = dt_time.fromisoformat(text[:5])
    except ValueError:
        return DEFAULT_SEND_TIME
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def _send_time_obj(value: str) -> dt_time:
    hour, minute = [int(part) for part in _parse_send_time(value).split(":", 1)]
    return dt_time(hour=hour, minute=minute)


def _normalize_recipients(value: Any) -> list[str]:
    if isinstance(value, str):
        source = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        source = value
    else:
        source = []
    seen: set[str] = set()
    result: list[str] = []
    for item in source:
        email = str(item or "").strip()
        key = email.lower()
        if "@" not in email or key in seen:
            continue
        seen.add(key)
        result.append(email)
    return result


def ensure_fleet_daily_report_settings() -> None:
    execute(FLEET_REPORT_SETTINGS_SQL)


def load_fleet_daily_report_settings() -> dict[str, Any]:
    ensure_fleet_daily_report_settings()
    rows = fetch_all(
        """
        SELECT enabled, send_time, recipients, last_sent_date, updated_at
        FROM fleet_daily_report_settings
        WHERE singleton_key = 'default'
        LIMIT 1
        """
    )
    row = dict(rows[0]) if rows else {}
    recipients = row.get("recipients")
    if isinstance(recipients, str):
        try:
            recipients = json.loads(recipients)
        except json.JSONDecodeError:
            recipients = []
    return {
        "enabled": bool(row.get("enabled")),
        "send_time": _parse_send_time(row.get("send_time")),
        "recipients": _normalize_recipients(recipients),
        "fallback_recipients": _normalize_recipients(load_email_recipients_from_db() or []),
        "last_sent_date": _iso_date(row.get("last_sent_date")),
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else "",
    }


def save_fleet_daily_report_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    enabled = bool(source.get("enabled"))
    send_time = _parse_send_time(source.get("send_time"))
    recipients = _normalize_recipients(source.get("recipients"))
    ensure_fleet_daily_report_settings()
    execute(
        """
        UPDATE fleet_daily_report_settings
        SET enabled = %s,
            send_time = %s,
            recipients = CAST(%s AS jsonb),
            updated_at = now()
        WHERE singleton_key = 'default'
        """,
        (enabled, send_time, json.dumps(recipients)),
    )
    return load_fleet_daily_report_settings()


def mark_fleet_daily_report_sent(report_date: date) -> None:
    ensure_fleet_daily_report_settings()
    execute(
        """
        UPDATE fleet_daily_report_settings
        SET last_sent_date = %s,
            updated_at = now()
        WHERE singleton_key = 'default'
        """,
        (report_date,),
    )


def _vehicle_subtype_label(value: Any) -> str:
    key = str(value or "").strip().lower()
    return SUBTYPE_LABELS.get(key, key.replace("_", " ").title() if key else "Sin especificar")


def _local_bounds(report_date: date) -> tuple[datetime, datetime]:
    start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=ECUADOR_TZ)
    return start, start + timedelta(days=1)


def _month_bounds(report_date: date) -> tuple[datetime, datetime]:
    start = datetime(report_date.year, report_date.month, 1, tzinfo=ECUADOR_TZ)
    _, day_end = _local_bounds(report_date)
    return start, day_end


def _fmt_datetime(value: Any) -> str:
    if not value:
        return "--"
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text[:19]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ECUADOR_TZ).strftime("%Y-%m-%d %H:%M")


def _fmt_time(value: Any) -> str:
    text = _fmt_datetime(value)
    return text[-5:] if text and text != "--" else "--"


def _fmt_coord(lat: Any, lon: Any) -> str:
    try:
        return f"{float(lat):.6f}, {float(lon):.6f}"
    except (TypeError, ValueError):
        return "--"


def _fmt_minutes(minutes: Any) -> str:
    total = max(0, int(round(float(minutes or 0))))
    hours, mins = divmod(total, 60)
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


def _fmt_geofence_exit(interval: dict[str, Any]) -> str:
    if str(interval.get("status") or "").lower() == "permanece":
        return "permanece"
    return _fmt_time(interval.get("exit_at"))


def fetch_daily_vehicle_km(report_date: date) -> list[dict[str, Any]]:
    local_start, local_end = _local_bounds(report_date)
    rows = fetch_all(
        """
        WITH vehicle_base AS (
            SELECT
                v.id::text AS source_vehicle_id,
                NULLIF(v.name, '') AS name,
                NULLIF(v.plate, '') AS plate,
                NULLIF(v.unique_code, '') AS unique_code,
                NULLIF(v.driver_name, '') AS driver_name,
                NULLIF(v.vehicle_type, '') AS vehicle_type,
                NULLIF(v.vehicle_subtype, '') AS vehicle_subtype,
                NULLIF(v.make, '') AS make,
                NULLIF(v.model, '') AS model,
                v.year AS year,
                SUBSTRING(UPPER(COALESCE(v.plate, v.name, v.unique_code, '')) FROM '([A-Z]{2,4}[ -]?[0-9]{3,5})') AS plate_match
            FROM vehicles v
            WHERE v.active IS TRUE
              AND v.deleted_at IS NULL
              AND COALESCE(v.vehicle_type, 'auto') NOT LIKE 'drone%%'
        ),
        scoped_vehicles AS (
            SELECT
                vb.source_vehicle_id,
                COALESCE(
                    NULLIF(UPPER(REGEXP_REPLACE(vb.plate_match, '^([A-Z]{2,4})[ -]?([0-9]{3,5})$', '\\1-\\2')), ''),
                    vb.plate,
                    vb.name,
                    vb.unique_code,
                    vb.source_vehicle_id
                ) AS label,
                COALESCE(
                    NULLIF(REGEXP_REPLACE(UPPER(vb.plate_match), '[^A-Z0-9]', '', 'g'), ''),
                    NULLIF(REGEXP_REPLACE(UPPER(COALESCE(vb.plate, vb.name, vb.unique_code, vb.source_vehicle_id)), '[^A-Z0-9]', '', 'g'), ''),
                    vb.source_vehicle_id
                ) AS fleet_key,
                vb.plate,
                vb.driver_name,
                vb.vehicle_type,
                vb.vehicle_subtype,
                vb.make,
                vb.model,
                vb.year
            FROM vehicle_base vb
        ),
        logical_vehicles AS (
            SELECT
                sv.fleet_key AS vehicle_id,
                MIN(sv.label)::text AS label,
                COALESCE(MIN(sv.plate), MIN(sv.label))::text AS plate,
                MIN(sv.driver_name)::text AS driver_name,
                MIN(sv.vehicle_type)::text AS vehicle_type,
                MIN(sv.vehicle_subtype)::text AS vehicle_subtype,
                MIN(sv.make)::text AS make,
                MIN(sv.model)::text AS model,
                MIN(sv.year)::int AS year,
                STRING_AGG(DISTINCT sv.source_vehicle_id, ',') AS source_vehicle_ids,
                COUNT(DISTINCT sv.source_vehicle_id)::bigint AS source_count
            FROM scoped_vehicles sv
            GROUP BY sv.fleet_key
        ),
        points AS (
            SELECT
                vt.id,
                vt.vehicle_id::text AS source_vehicle_id,
                sv.fleet_key AS vehicle_id,
                vt.latitude,
                vt.longitude,
                vt.speed,
                vt.received_at,
                CASE
                    WHEN (vt.payload->>'gps_datetime_iso') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                    THEN (vt.payload->>'gps_datetime_iso')::timestamptz
                    ELSE vt.received_at
                END AS gps_at
            FROM vehicle_telemetry vt
            JOIN scoped_vehicles sv ON sv.source_vehicle_id = vt.vehicle_id::text
            WHERE vt.received_at >= %s
              AND vt.received_at < %s
              AND vt.latitude IS NOT NULL
              AND vt.longitude IS NOT NULL
              AND vt.latitude BETWEEN -90 AND 90
              AND vt.longitude BETWEEN -180 AND 180
              AND NOT (ABS(vt.latitude) < 0.000001 AND ABS(vt.longitude) < 0.000001)
        ),
        day_points AS (
            SELECT
                p.*,
                (p.gps_at AT TIME ZONE 'America/Guayaquil')::date AS local_day
            FROM points p
            WHERE p.gps_at >= %s
              AND p.gps_at < %s
        ),
        ordered AS (
            SELECT
                dp.*,
                LAG(dp.latitude) OVER w AS prev_latitude,
                LAG(dp.longitude) OVER w AS prev_longitude,
                LAG(dp.gps_at) OVER w AS prev_gps_at,
                LAG(dp.local_day) OVER w AS prev_local_day
            FROM day_points dp
            WINDOW w AS (PARTITION BY dp.vehicle_id ORDER BY dp.gps_at ASC, dp.received_at ASC, dp.id ASC)
        ),
        distance_calc AS (
            SELECT
                o.*,
                EXTRACT(EPOCH FROM (o.gps_at - o.prev_gps_at)) AS elapsed_seconds,
                CASE
                    WHEN o.prev_latitude IS NULL THEN NULL
                    ELSE LEAST(
                        1.0,
                        GREATEST(
                            0.0,
                            POWER(SIN(RADIANS(o.latitude - o.prev_latitude) / 2), 2)
                            + COS(RADIANS(o.prev_latitude))
                              * COS(RADIANS(o.latitude))
                              * POWER(SIN(RADIANS(o.longitude - o.prev_longitude) / 2), 2)
                        )
                    )
                END AS haversine_a
            FROM ordered o
        ),
        segments AS (
            SELECT
                dc.*,
                CASE
                    WHEN dc.haversine_a IS NULL THEN 0.0
                    ELSE 6371.0 * 2.0 * ATAN2(SQRT(dc.haversine_a), SQRT(GREATEST(0.0, 1.0 - dc.haversine_a)))
                END AS distance_km
            FROM distance_calc dc
        ),
        aggregate_rows AS (
            SELECT
                s.vehicle_id,
                COUNT(*)::bigint AS total_points,
                MAX(COALESCE(s.speed, 0)) AS max_speed,
                SUM(
                    CASE
                        WHEN s.prev_latitude IS NOT NULL
                          AND s.local_day = s.prev_local_day
                          AND s.elapsed_seconds > 0
                          AND s.elapsed_seconds <= %s
                          AND s.distance_km <= %s
                          AND (s.distance_km / (s.elapsed_seconds / 3600.0)) <= %s
                        THEN s.distance_km
                        ELSE 0
                    END
                ) AS total_km
            FROM segments s
            GROUP BY s.vehicle_id
        ),
        start_points AS (
            SELECT DISTINCT ON (vehicle_id)
                vehicle_id, gps_at AS start_at, latitude AS start_lat, longitude AS start_lon
            FROM day_points
            ORDER BY vehicle_id, gps_at ASC, received_at ASC, id ASC
        ),
        end_points AS (
            SELECT DISTINCT ON (vehicle_id)
                vehicle_id, gps_at AS end_at, latitude AS end_lat, longitude AS end_lon
            FROM day_points
            ORDER BY vehicle_id, gps_at DESC, received_at DESC, id DESC
        )
        SELECT
            lv.vehicle_id,
            lv.label,
            lv.plate,
            lv.driver_name,
            lv.vehicle_type,
            lv.vehicle_subtype,
            lv.make,
            lv.model,
            lv.year,
            lv.source_vehicle_ids,
            lv.source_count,
            COALESCE(ar.total_km, 0)::double precision AS total_km,
            COALESCE(ar.total_points, 0)::bigint AS total_points,
            COALESCE(ar.max_speed, 0)::double precision AS max_speed,
            sp.start_at,
            sp.start_lat,
            sp.start_lon,
            ep.end_at,
            ep.end_lat,
            ep.end_lon
        FROM logical_vehicles lv
        LEFT JOIN aggregate_rows ar ON ar.vehicle_id = lv.vehicle_id
        LEFT JOIN start_points sp ON sp.vehicle_id = lv.vehicle_id
        LEFT JOIN end_points ep ON ep.vehicle_id = lv.vehicle_id
        ORDER BY COALESCE(ar.total_km, 0) DESC, lv.label ASC
        """,
        (
            local_start.astimezone(timezone.utc),
            local_end.astimezone(timezone.utc),
            local_start.astimezone(timezone.utc),
            local_end.astimezone(timezone.utc),
            MAX_SEGMENT_GAP_SECONDS,
            MAX_SEGMENT_DISTANCE_KM,
            MAX_REASONABLE_SPEED_KMH,
        ),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["total_km"] = round(float(item.get("total_km") or 0.0), 2)
        item["total_points"] = int(item.get("total_points") or 0)
        item["max_speed"] = round(float(item.get("max_speed") or 0.0), 1)
        item["source_count"] = int(item.get("source_count") or 1)
        item["source_vehicle_ids"] = str(item.get("source_vehicle_ids") or "").split(",") if item.get("source_vehicle_ids") else []
        item["vehicle_subtype_name"] = _vehicle_subtype_label(item.get("vehicle_subtype"))
        item["driver_name"] = item.get("driver_name") or ""
        item["chofer"] = item["driver_name"]
        item["make"] = item.get("make") or ""
        item["model"] = item.get("model") or ""
        item["year"] = int(item["year"]) if item.get("year") else None
        result.append(item)
    return result


def fetch_monthly_vehicle_summary(report_date: date) -> dict[str, dict[str, Any]]:
    month_start, month_end = _month_bounds(report_date)
    rows = fetch_all(
        """
        WITH vehicle_base AS (
            SELECT
                v.id::text AS source_vehicle_id,
                NULLIF(v.name, '') AS name,
                NULLIF(v.plate, '') AS plate,
                NULLIF(v.unique_code, '') AS unique_code,
                SUBSTRING(UPPER(COALESCE(v.plate, v.name, v.unique_code, '')) FROM '([A-Z]{2,4}[ -]?[0-9]{3,5})') AS plate_match
            FROM vehicles v
            WHERE v.active IS TRUE
              AND v.deleted_at IS NULL
              AND COALESCE(v.vehicle_type, 'auto') NOT LIKE 'drone%%'
        ),
        scoped_vehicles AS (
            SELECT
                vb.source_vehicle_id,
                COALESCE(
                    NULLIF(REGEXP_REPLACE(UPPER(vb.plate_match), '[^A-Z0-9]', '', 'g'), ''),
                    NULLIF(REGEXP_REPLACE(UPPER(COALESCE(vb.plate, vb.name, vb.unique_code, vb.source_vehicle_id)), '[^A-Z0-9]', '', 'g'), ''),
                    vb.source_vehicle_id
                ) AS fleet_key
            FROM vehicle_base vb
        ),
        logical_vehicles AS (
            SELECT DISTINCT sv.fleet_key AS vehicle_id
            FROM scoped_vehicles sv
        ),
        points AS (
            SELECT
                vt.id,
                sv.fleet_key AS vehicle_id,
                vt.latitude,
                vt.longitude,
                vt.speed,
                vt.received_at,
                CASE
                    WHEN (vt.payload->>'gps_datetime_iso') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                    THEN (vt.payload->>'gps_datetime_iso')::timestamptz
                    ELSE vt.received_at
                END AS gps_at
            FROM vehicle_telemetry vt
            JOIN scoped_vehicles sv ON sv.source_vehicle_id = vt.vehicle_id::text
            WHERE vt.received_at >= %s
              AND vt.received_at < %s
              AND vt.latitude IS NOT NULL
              AND vt.longitude IS NOT NULL
              AND vt.latitude BETWEEN -90 AND 90
              AND vt.longitude BETWEEN -180 AND 180
              AND NOT (ABS(vt.latitude) < 0.000001 AND ABS(vt.longitude) < 0.000001)
        ),
        month_points AS (
            SELECT
                p.*,
                (p.gps_at AT TIME ZONE 'America/Guayaquil')::date AS local_day
            FROM points p
            WHERE p.gps_at >= %s
              AND p.gps_at < %s
        ),
        ordered AS (
            SELECT
                mp.*,
                LAG(mp.latitude) OVER w AS prev_latitude,
                LAG(mp.longitude) OVER w AS prev_longitude,
                LAG(mp.gps_at) OVER w AS prev_gps_at,
                LAG(mp.local_day) OVER w AS prev_local_day
            FROM month_points mp
            WINDOW w AS (PARTITION BY mp.vehicle_id ORDER BY mp.gps_at ASC, mp.received_at ASC, mp.id ASC)
        ),
        distance_calc AS (
            SELECT
                o.*,
                EXTRACT(EPOCH FROM (o.gps_at - o.prev_gps_at)) AS elapsed_seconds,
                CASE
                    WHEN o.prev_latitude IS NULL THEN NULL
                    ELSE LEAST(
                        1.0,
                        GREATEST(
                            0.0,
                            POWER(SIN(RADIANS(o.latitude - o.prev_latitude) / 2), 2)
                            + COS(RADIANS(o.prev_latitude))
                              * COS(RADIANS(o.latitude))
                              * POWER(SIN(RADIANS(o.longitude - o.prev_longitude) / 2), 2)
                        )
                    )
                END AS haversine_a
            FROM ordered o
        ),
        segments AS (
            SELECT
                dc.*,
                CASE
                    WHEN dc.haversine_a IS NULL THEN 0.0
                    ELSE 6371.0 * 2.0 * ATAN2(SQRT(dc.haversine_a), SQRT(GREATEST(0.0, 1.0 - dc.haversine_a)))
                END AS distance_km
            FROM distance_calc dc
        ),
        daily_totals AS (
            SELECT
                s.vehicle_id,
                s.local_day,
                SUM(
                    CASE
                        WHEN s.prev_latitude IS NOT NULL
                          AND s.local_day = s.prev_local_day
                          AND s.elapsed_seconds > 0
                          AND s.elapsed_seconds <= %s
                          AND s.distance_km <= %s
                          AND (s.distance_km / (s.elapsed_seconds / 3600.0)) <= %s
                        THEN s.distance_km
                        ELSE 0
                    END
                ) AS day_km
            FROM segments s
            GROUP BY s.vehicle_id, s.local_day
        ),
        monthly_agg AS (
            SELECT
                dt.vehicle_id,
                SUM(dt.day_km)::double precision AS month_km,
                COUNT(*) FILTER (WHERE dt.day_km > 0.05)::bigint AS active_days
            FROM daily_totals dt
            GROUP BY dt.vehicle_id
        )
        SELECT
            lv.vehicle_id,
            COALESCE(ma.month_km, 0)::double precision AS month_km,
            COALESCE(ma.active_days, 0)::bigint AS active_days
        FROM logical_vehicles lv
        LEFT JOIN monthly_agg ma ON ma.vehicle_id = lv.vehicle_id
        """,
        (
            month_start.astimezone(timezone.utc),
            month_end.astimezone(timezone.utc),
            month_start.astimezone(timezone.utc),
            month_end.astimezone(timezone.utc),
            MAX_SEGMENT_GAP_SECONDS,
            MAX_SEGMENT_DISTANCE_KM,
            MAX_REASONABLE_SPEED_KMH,
        ),
    )
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        vehicle_id = str(row.get("vehicle_id") or "")
        month_km = round(float(row.get("month_km") or 0.0), 2)
        active_days = int(row.get("active_days") or 0)
        avg_km_active_day = round(month_km / active_days, 2) if active_days else 0.0
        summary[vehicle_id] = {
            "month_km": month_km,
            "active_days": active_days,
            "avg_km_active_day": avg_km_active_day,
        }
    return summary


def fetch_geofence_intervals(report_date: date) -> list[dict[str, Any]]:
    local_start, local_end = _local_bounds(report_date)
    rows = fetch_all(
        """
        WITH vehicle_base AS (
            SELECT
                v.id::text AS source_vehicle_id,
                NULLIF(v.name, '') AS name,
                NULLIF(v.plate, '') AS plate,
                NULLIF(v.unique_code, '') AS unique_code,
                NULLIF(v.driver_name, '') AS driver_name,
                NULLIF(v.vehicle_type, '') AS vehicle_type,
                NULLIF(v.vehicle_subtype, '') AS vehicle_subtype,
                SUBSTRING(UPPER(COALESCE(v.plate, v.name, v.unique_code, '')) FROM '([A-Z]{2,4}[ -]?[0-9]{3,5})') AS plate_match
            FROM vehicles v
            WHERE v.active IS TRUE
              AND v.deleted_at IS NULL
              AND COALESCE(v.vehicle_type, 'auto') NOT LIKE 'drone%%'
        ),
        scoped_vehicles AS (
            SELECT
                vb.source_vehicle_id,
                COALESCE(
                    NULLIF(UPPER(REGEXP_REPLACE(vb.plate_match, '^([A-Z]{2,4})[ -]?([0-9]{3,5})$', '\\1-\\2')), ''),
                    vb.plate,
                    vb.name,
                    vb.unique_code,
                    vb.source_vehicle_id
                ) AS label,
                COALESCE(
                    NULLIF(REGEXP_REPLACE(UPPER(vb.plate_match), '[^A-Z0-9]', '', 'g'), ''),
                    NULLIF(REGEXP_REPLACE(UPPER(COALESCE(vb.plate, vb.name, vb.unique_code, vb.source_vehicle_id)), '[^A-Z0-9]', '', 'g'), ''),
                    vb.source_vehicle_id
                ) AS fleet_key,
                vb.plate,
                vb.driver_name,
                vb.vehicle_type,
                vb.vehicle_subtype
            FROM vehicle_base vb
        ),
        scoped_alerts AS (
            SELECT
                sv.fleet_key AS vehicle_id,
                a.vehicle_id::text AS source_vehicle_id,
                sv.label,
                sv.plate,
                sv.driver_name,
                sv.vehicle_type,
                sv.vehicle_subtype,
                a.geofence_id::text AS geofence_id,
                a.geofence_name,
                a.event_type,
                COALESCE(a.gps_at, a.recorded_at) AS event_at
            FROM geofence_alerts a
            JOIN scoped_vehicles sv ON sv.source_vehicle_id = a.vehicle_id::text
            WHERE COALESCE(a.gps_at, a.recorded_at) < %s
        ),
        previous_events AS (
            SELECT DISTINCT ON (vehicle_id, geofence_id, source_vehicle_id)
                true AS is_previous,
                *
            FROM scoped_alerts
            WHERE event_at < %s
            ORDER BY vehicle_id, geofence_id, source_vehicle_id, event_at DESC
        ),
        day_events AS (
            SELECT
                false AS is_previous,
                *
            FROM scoped_alerts
            WHERE event_at >= %s
              AND event_at < %s
        )
        SELECT *
        FROM previous_events
        UNION ALL
        SELECT *
        FROM day_events
        ORDER BY vehicle_id, geofence_id, event_at ASC, is_previous DESC
        """,
        (
            local_end.astimezone(timezone.utc),
            local_start.astimezone(timezone.utc),
            local_start.astimezone(timezone.utc),
            local_end.astimezone(timezone.utc),
        ),
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        key = (str(item.get("vehicle_id")), str(item.get("geofence_id")))
        grouped[key].append(item)

    intervals: list[dict[str, Any]] = []
    for (_vehicle_id, _geofence_id), items in grouped.items():
        items.sort(key=lambda item: (item.get("event_at") or datetime.min.replace(tzinfo=timezone.utc), bool(item.get("is_previous"))))
        previous = next((item for item in reversed(items) if item.get("is_previous")), None)
        day_events = [item for item in items if not item.get("is_previous")]
        inside = str(previous.get("event_type") if previous else "").lower() == "entry"
        entry_at = local_start if inside else None
        template = previous or (day_events[0] if day_events else {})
        group_intervals: list[dict[str, Any]] = []

        for event in day_events:
            event_at = event.get("event_at")
            if isinstance(event_at, datetime):
                event_local = event_at.astimezone(ECUADOR_TZ)
            else:
                continue
            event_type = str(event.get("event_type") or "").lower()
            template = event
            if event_type == "entry":
                inside = True
                entry_at = max(event_local, local_start)
                continue
            if event_type == "exit":
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
            end = local_end
            if end > start:
                group_intervals.append(_geofence_interval_item(template, start, end, "permanece"))
        intervals.extend(group_intervals)

    intervals = _resolve_vehicle_geofence_overlaps(intervals)
    intervals.sort(key=_geofence_interval_sort_key)
    return intervals


def _geofence_interval_item(template: dict[str, Any], entry_at: datetime, exit_at: datetime, status: str) -> dict[str, Any]:
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


def _extend_last_geofence_interval(interval: dict[str, Any], exit_at: datetime) -> None:
    entry_at = _datetime_from_iso(interval.get("entry_at"))
    current_exit = _datetime_from_iso(interval.get("exit_at"))
    if not entry_at or (current_exit and exit_at <= current_exit):
        return
    interval["exit_at"] = exit_at.isoformat()
    interval["duration_minutes"] = round(max(0.0, (exit_at - entry_at).total_seconds() / 60), 1)
    interval["status"] = "salio"


def _resolve_vehicle_geofence_overlaps(intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_vehicle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for interval in intervals:
        by_vehicle[str(interval.get("vehicle_id") or "")].append(interval)

    resolved: list[dict[str, Any]] = []
    for vehicle_intervals in by_vehicle.values():
        selected: list[dict[str, Any]] = []
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


def _geofence_interval_time_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("entry_at") or ""),
        str(item.get("exit_at") or ""),
        str(item.get("vehicle_label") or ""),
        str(item.get("geofence_name") or ""),
    )


def _geofence_interval_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("entry_at") or ""),
        str(item.get("vehicle_label") or ""),
        str(item.get("geofence_name") or ""),
    )


def _datetime_from_iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


_SUBTYPE_SORT_RANK = {"volqueta": 0, "camion": 1, "camioneta": 2}


def _subtype_sort_rank(vehicle: dict[str, Any]) -> int:
    key = str(vehicle.get("vehicle_subtype") or "").strip().lower()
    return _SUBTYPE_SORT_RANK.get(key, 10)


def build_daily_fleet_report(report_date: date | str | None = None) -> dict[str, Any]:
    day = _parse_date(report_date)
    vehicles = fetch_daily_vehicle_km(day)
    geofence_intervals = fetch_geofence_intervals(day)
    monthly_summary = fetch_monthly_vehicle_summary(day)
    intervals_by_vehicle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for interval in geofence_intervals:
        intervals_by_vehicle[str(interval.get("vehicle_id") or "")].append(interval)

    for vehicle in vehicles:
        vehicle["geofence_intervals"] = intervals_by_vehicle.get(str(vehicle.get("vehicle_id") or ""), [])
        month_stats = monthly_summary.get(str(vehicle.get("vehicle_id") or ""), {})
        vehicle["month_km"] = month_stats.get("month_km", 0.0)
        vehicle["active_days"] = month_stats.get("active_days", 0)
        vehicle["avg_km_active_day"] = month_stats.get("avg_km_active_day", 0.0)

    vehicles.sort(
        key=lambda v: (
            _subtype_sort_rank(v),
            -float(v.get("total_km") or 0.0),
            str(v.get("label") or v.get("plate") or v.get("vehicle_id") or ""),
        )
    )

    totals = {
        "total_km": round(sum(float(item.get("total_km") or 0.0) for item in vehicles), 2),
        "active_vehicles": sum(1 for item in vehicles if float(item.get("total_km") or 0.0) > 0.05),
        "total_vehicles": len(vehicles),
        "total_points": sum(int(item.get("total_points") or 0) for item in vehicles),
        "geofence_intervals": len(geofence_intervals),
        "geofence_minutes": round(sum(float(item.get("duration_minutes") or 0.0) for item in geofence_intervals), 1),
    }
    return {
        "date": day.isoformat(),
        "generated_at": _now_local().isoformat(),
        "totals": totals,
        "vehicles": vehicles,
        "geofence_intervals": geofence_intervals,
    }


def _pdf_escape(value: str) -> str:
    text = str(value or "").encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


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

    def _ensure_space(self, height: float) -> None:
        if self.y - height < self.margin - 6:
            self.new_page()

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
        page_count = len(self.pages)
        catalog_id = 1
        pages_id = 2
        font_regular_id = 3
        font_mono_id = 4
        font_bold_id = 5
        first_page_id = 6
        page_ids = [first_page_id + index * 2 for index in range(page_count)]
        content_ids = [page_id + 1 for page_id in page_ids]

        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("latin-1"))
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        for page_id, content_id, commands in zip(page_ids, content_ids, self.pages):
            resources = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>"
            page = (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.page_width:.0f} {self.page_height:.0f}] "
                f"/Resources {resources} /Contents {content_id} 0 R >>"
            )
            stream = "\n".join(commands).encode("latin-1", "replace")
            content = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
            objects.append(page.encode("latin-1"))
            objects.append(content)

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
        output.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
        )
        return bytes(output)

    def _top_y(self) -> float:
        return self.page_height - self.margin - 4


def _fit(value: Any, width: int) -> str:
    text = str(value or "")
    if len(text) <= width:
        return text.ljust(width)
    return (text[: max(0, width - 3)] + "...").ljust(width)


def _table_line(values: list[Any], widths: list[int]) -> str:
    return "  ".join(_fit(value, width) for value, width in zip(values, widths))


def build_fleet_report_pdf(report: dict[str, Any]) -> bytes:
    pdf = _SimplePdf(page_width=842, page_height=595)
    report_date = str(report.get("date") or "")
    totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
    vehicles = report.get("vehicles") if isinstance(report.get("vehicles"), list) else []

    pdf.text("Reporte diario de flota", size=18, font="F3")
    pdf.text(f"Fecha operativa: {report_date}", size=11, font="F3")
    pdf.text(f"Generado: {_fmt_datetime(report.get('generated_at'))}", size=9)
    pdf.rule()
    pdf.text(
        f"Km flota: {float(totals.get('total_km') or 0):.2f} | "
        f"Vehículos activos: {totals.get('active_vehicles', 0)} / {totals.get('total_vehicles', 0)} | "
        f"Eventos de geocerca: {totals.get('geofence_intervals', 0)}",
        size=10,
        font="F3",
    )
    pdf.spacer()

    pdf.text("Resumen de vehículos", size=13, font="F3")
    # Anchos de columnas del resumen.
    # Orden: Vehículo, Marca, Modelo, Año, Chofer, Tipo, Km día, Km mes, D.act, Km/día
    widths = [
        12,  # Vehículo
        15,  # Marca
        30,  # Modelo
        6,   # Año
        20,  # Chofer
        17,  # Tipo
        8,   # Km día
        8,   # Km mes
        5,   # D.act
        8,   # Km/día
    ]
    pdf.text(
        _table_line(
            ["Vehículo", "Marca", "Modelo", "Año", "Chofer", "Tipo", "Km día", "Km mes", "D.act", "Km/día"],
            widths,
        ),
        font="F2",
        size=8,
    )
    pdf.rule()
    for vehicle in vehicles:
        pdf.text(
            _table_line(
                [
                    vehicle.get("label") or vehicle.get("plate") or vehicle.get("vehicle_id"),
                    vehicle.get("make") or vehicle.get("brand") or "--",
                    vehicle.get("model") or "--",
                    vehicle.get("year") or "--",
                    vehicle.get("driver_name") or "--",
                    vehicle.get("vehicle_subtype_name") or "--",
                    f"{float(vehicle.get('total_km') or 0):.2f}",
                    f"{float(vehicle.get('month_km') or 0):.2f}",
                    int(vehicle.get("active_days") or 0),
                    f"{float(vehicle.get('avg_km_active_day') or 0):.2f}",
                ],
                widths,
            ),
            font="F2",
            size=8,
        )

    pdf.new_page()
    pdf.text("Detalle por vehículo", size=16, font="F3")
    pdf.rule()

    for vehicle in vehicles:
        title = vehicle.get("label") or vehicle.get("plate") or vehicle.get("vehicle_id")
        vehicle_intervals = vehicle.get("geofence_intervals") if isinstance(vehicle.get("geofence_intervals"), list) else []

        pdf.text(str(title), size=12, font="F3", gap=14)
        pdf.text(
            f"Placa: {vehicle.get('plate') or '--'}     "
            f"Chofer: {vehicle.get('driver_name') or '--'}     "
            f"Tipo: {vehicle.get('vehicle_subtype_name') or '--'}",
            size=9,
            gap=12,
        )
        pdf.text(
            f"Marca: {vehicle.get('make') or '--'}     "
            f"Modelo: {vehicle.get('model') or '--'}     "
            f"Año: {vehicle.get('year') or '--'}",
            size=9,
            gap=12,
        )
        pdf.text(
            f"Km del día: {float(vehicle.get('total_km') or 0):.2f}     "
            f"Km acumulado del mes: {float(vehicle.get('month_km') or 0):.2f}     "
            f"Días activos del mes: {int(vehicle.get('active_days') or 0)}     "
            f"Promedio km/día activo: {float(vehicle.get('avg_km_active_day') or 0):.2f}",
            size=9,
            gap=12,
        )
        pdf.text(
            f"Ruta: {_fmt_time(vehicle.get('start_at'))} "
            f"{_fmt_coord(vehicle.get('start_lat'), vehicle.get('start_lon'))}  ->  "
            f"{_fmt_time(vehicle.get('end_at'))} "
            f"{_fmt_coord(vehicle.get('end_lat'), vehicle.get('end_lon'))}",
            size=9,
            gap=12,
        )

        if vehicle_intervals:
            pdf.text("Geocercas:", size=9, font="F3", gap=11)
            geofence_widths = [32, 10, 10, 13, 12]
            pdf.text(
                _table_line(
                    ["Geocerca", "Ingreso", "Salida", "Permanencia", "Estado"],
                    geofence_widths,
                ),
                font="F2",
                size=8,
                x=58,
                gap=10,
            )
            for interval in vehicle_intervals:
                pdf.text(
                    _table_line(
                        [
                            interval.get("geofence_name") or "--",
                            _fmt_time(interval.get("entry_at")),
                            _fmt_geofence_exit(interval),
                            _fmt_minutes(interval.get("duration_minutes")),
                            interval.get("status") or "--",
                        ],
                        geofence_widths,
                    ),
                    font="F2",
                    size=8,
                    x=58,
                    gap=10,
                )
        else:
            pdf.text("Geocercas: sin permanencias registradas.", size=8, x=58, gap=10)

        pdf.spacer(4)
        pdf.rule()
        pdf.spacer(4)

    return pdf.build()

def send_fleet_report_for_date(
    report_date: date | str | None = None,
    *,
    recipients: list[str] | str | None = None,
    mark_sent: bool = False,
) -> dict[str, Any]:
    day = _parse_date(report_date)
    settings = load_fleet_daily_report_settings()
    target_recipients = _normalize_recipients(recipients)
    if not target_recipients:
        target_recipients = settings.get("recipients") or []
    if not target_recipients:
        target_recipients = load_email_recipients_from_db() or []
    target_recipients = _normalize_recipients(target_recipients)
    if not target_recipients:
        raise ValueError("No hay correos configurados para el reporte diario.")

    report = build_daily_fleet_report(day)
    pdf_bytes = build_fleet_report_pdf(report)
    email_settings = dict(load_notification_settings().get("email", {}))
    email_settings["recipients"] = target_recipients
    email_settings["subject"] = f"Reporte diario de flota - {day.isoformat()}"
    email_settings["message"] = (
        "Adjunto se envía el reporte diario de flota en PDF.\n\n"
        f"Fecha operativa: {day.isoformat()}\n"
        f"Km totales: {float(report['totals'].get('total_km') or 0):.2f}\n"
        f"Vehículos activos: {report['totals'].get('active_vehicles')} / {report['totals'].get('total_vehicles')}\n"
    )
    email_settings["attachments"] = [
        {
            "filename": f"reporte_flota_{day.isoformat()}.pdf",
            "content": pdf_bytes,
            "mime_type": "application/pdf",
        }
    ]
    sent = send_email(email_settings)
    if mark_sent:
        mark_fleet_daily_report_sent(day)
    return {
        "ok": True,
        "date": day.isoformat(),
        "sent": sent,
        "total": len(sent),
        "report": {
            "totals": report.get("totals", {}),
            "vehicles": len(report.get("vehicles") or []),
            "geofence_intervals": len(report.get("geofence_intervals") or []),
        },
    }


class FleetDailyReportWorker:
    def __init__(self, *, poll_interval: float = 300.0) -> None:
        self.poll_interval = max(60.0, float(poll_interval))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "running": False,
            "last_checked_at": "",
            "last_sent_date": "",
            "last_sent_total": 0,
            "last_error": "",
            "next_report_date": "",
        }

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="fleet-daily-report", daemon=True)
        self._thread.start()
        self._set_status(running=True)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._set_status(running=False)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def check_once(self) -> dict[str, Any]:
        now = _now_local()
        self._set_status(last_checked_at=now.isoformat(), last_error="")
        settings = load_fleet_daily_report_settings()
        report_date = now.date() - timedelta(days=1)
        self._set_status(next_report_date=report_date.isoformat())
        if not settings.get("enabled"):
            return {"ok": True, "sent": [], "skipped": "disabled"}
        if str(settings.get("last_sent_date") or "") >= report_date.isoformat():
            return {"ok": True, "sent": [], "skipped": "already_sent"}
        if now.time() < _send_time_obj(str(settings.get("send_time") or DEFAULT_SEND_TIME)):
            return {"ok": True, "sent": [], "skipped": "not_due"}
        result = send_fleet_report_for_date(report_date, mark_sent=True)
        self._set_status(
            last_sent_date=result.get("date", ""),
            last_sent_total=int(result.get("total") or 0),
        )
        return result

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception as exc:
                LOG.warning("No se pudo procesar el reporte diario de flota: %s", exc)
                self._set_status(last_error=str(exc), last_checked_at=_now_local().isoformat())
            finally:
                self._stop_event.wait(self.poll_interval)
        self._set_status(running=False)

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)
