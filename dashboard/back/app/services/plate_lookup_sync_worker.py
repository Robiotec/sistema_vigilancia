from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from back.app.config import get_settings
from back.app.services.plate_lookup_client import PlateLookupClient, normalize_plate
from back.app.services.remote_detection_feed import RemoteDetectionFeedService


READY_STATUSES = {"completed", "completed_with_errors"}
RETRYABLE_REMOTE_STATUSES = {
    "pending_remote_lookup",
    "running_remote_lookup",
    "remote_lookup_unavailable",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def vehicle_info_from_record(record: dict[str, Any]) -> dict[str, Any]:
    def get(*keys: str) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return None

    return {
        "Placa": get("placa"),
        "Propietario": get("propietario"),
        "Marca": get("marca"),
        "Modelo": get("modelo"),
        "Color": " / ".join(str(v) for v in (get("color_1"), get("color_2")) if v) or None,
        "Año Vehículo": get("anio"),
        "Tipo Servicio": get("servicio"),
        "Clase": get("clase"),
        "Tipo": get("tipo"),
        "Uso": get("uso"),
        "VIN": get("vin"),
        "Motor": get("motor"),
        "Cilindraje": get("cilindraje"),
        "Cantón Matrícula": get("canton_matricula"),
        "Fecha Matrícula": get("fecha_matricula"),
        "Caducidad Matrícula": get("vencimiento_matricula"),
        "Último Pago": get("ultimo_pago"),
        "Condición": get("estado"),
        "Información": get("informacion"),
    }


def merge_payload(payload: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    payload["vehicle_info_checked_at"] = utc_now_iso()
    payload["vehicle_info_source"] = "10.0.0.3 PlateLookupRecord"
    if not record:
        payload.setdefault("vehicle_info", None)
        payload["vehicle_info_status"] = "remote_lookup_unavailable"
        return payload

    ready = bool(record.get("ready")) or str(record.get("status") or "") in READY_STATUSES
    pending = bool(record.get("pending")) or str(record.get("status") or "") in {"pending", "running"}
    if ready:
        payload["vehicle_info"] = vehicle_info_from_record(record)
        payload["vehicle_info_status"] = "remote_lookup_ready"
    elif pending:
        payload.setdefault("vehicle_info", None)
        payload["vehicle_info_status"] = "pending_remote_lookup"
    else:
        payload.setdefault("vehicle_info", None)
        payload["vehicle_info_status"] = str(record.get("status") or "remote_lookup_unavailable")
    payload["vehicle_info_record"] = record
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza datos de placas desde 10.0.0.3 hacia camera_event_history.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--backoff-seconds", type=int, default=600)
    args = parser.parse_args()

    settings = get_settings()
    client = PlateLookupClient(settings)
    dsn = RemoteDetectionFeedService._psycopg_dsn(settings.database_url)
    selected = updated = pending = failed = 0

    query = """
        SELECT id, plate, detail_payload
        FROM camera_event_history
        WHERE event_type = 'plate'
          AND plate IS NOT NULL
          AND plate <> ''
          AND (
            detail_payload->'vehicle_info' IS NULL
            OR jsonb_typeof(detail_payload->'vehicle_info') = 'null'
            OR COALESCE(detail_payload->>'vehicle_info_status', '') IN (
                'pending_remote_lookup',
                'running_remote_lookup',
                'remote_lookup_unavailable'
            )
          )
          AND (
            detail_payload->>'vehicle_info_checked_at' IS NULL
            OR (detail_payload->>'vehicle_info_checked_at')::timestamptz < now() - (%s * interval '1 second')
          )
        ORDER BY detected_at DESC, updated_at DESC
        LIMIT %s
    """

    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (max(60, args.backoff_seconds), max(1, args.limit)))
            rows = cur.fetchall()

        for row in rows:
            selected += 1
            plate = normalize_plate(row.get("plate"))
            if not plate:
                continue
            record = client.lookup(plate)
            payload = row.get("detail_payload") if isinstance(row.get("detail_payload"), dict) else {}
            merged = merge_payload(payload, record)
            status = merged.get("vehicle_info_status")
            if status == "remote_lookup_ready":
                updated += 1
            elif status in RETRYABLE_REMOTE_STATUSES:
                pending += 1
            else:
                failed += 1

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE camera_event_history
                    SET detail_payload = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (Json(merged), row["id"]),
                )
            conn.commit()
            if args.sleep > 0:
                time.sleep(args.sleep)

    print(json.dumps({
        "selected": selected,
        "updated": updated,
        "pending": pending,
        "failed": failed,
        "backoff_seconds": max(60, args.backoff_seconds),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
