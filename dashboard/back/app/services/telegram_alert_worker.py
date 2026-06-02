"""Worker de outbox para alertas Telegram.

Usa SELECT ... FOR UPDATE SKIP LOCKED para que múltiples workers (uvicorn
multi-process) no procesen la misma alerta simultáneamente.

Flujo por fila:
  pending/failed + next_retry_at <= now()
    → processing
    → descargar archivo remoto si corresponde
    → enviar Telegram
    → sent (con sent_at) o failed (con backoff exponencial)
    → dead_letter tras MAX_ATTEMPTS intentos
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json, RealDictCursor

_log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
# Backoff en segundos por índice de intento (0-based)
_BACKOFF_SECONDS = (30, 60, 120, 300, 600)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS camera_alert_outbox (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_uid        text        NOT NULL,
    camera_id        text        NOT NULL,
    event_type       text        NOT NULL,
    status           text        NOT NULL DEFAULT 'pending',
    attempts         int         NOT NULL DEFAULT 0,
    next_retry_at    timestamptz NOT NULL DEFAULT now(),
    last_error       text,
    telegram_payload jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz,
    CONSTRAINT uq_camera_alert_outbox_event_uid UNIQUE (event_uid),
    CONSTRAINT ck_camera_alert_outbox_status CHECK (
        status IN ('pending','processing','sent','failed','dead_letter')
    )
);
CREATE INDEX IF NOT EXISTS idx_camera_alert_outbox_status_retry
    ON camera_alert_outbox (status, next_retry_at)
    WHERE status IN ('pending','failed');
"""


class TelegramAlertWorker:
    """Procesa entradas pendientes en camera_alert_outbox.

    Parámetros inyectados para facilitar pruebas unitarias:
      send_video_fn(message, local_path) -> dict  (clave 'sent': int)
      send_photo_fn(message, local_path) -> dict
      send_text_fn(message)              -> dict
      cache_remote_file_fn(remote_path)  -> Path  (descarga SFTP)
      render_video_fn(local_path)        -> Path  (ffmpeg → mp4 Telegram)
    """

    _schema_ensured: bool = False  # flag de clase, por proceso

    def __init__(
        self,
        db_dsn: str,
        send_video_fn: Callable[[str, Path], dict[str, Any]],
        send_photo_fn: Callable[[str, Path], dict[str, Any]],
        send_text_fn: Callable[[str], dict[str, Any]],
        cache_remote_file_fn: Callable[[str], Path],
        render_video_fn: Callable[[Path], Path],
    ) -> None:
        self._db_dsn = db_dsn
        self._send_video = send_video_fn
        self._send_photo = send_photo_fn
        self._send_text = send_text_fn
        self._cache_remote_file = cache_remote_file_fn
        self._render_video = render_video_fn

    # ------------------------------------------------------------------ public

    def ensure_schema(self) -> None:
        """Crea la tabla si no existe. Idempotente."""
        if TelegramAlertWorker._schema_ensured:
            return
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                conn.commit()
            TelegramAlertWorker._schema_ensured = True
        except Exception as exc:
            _log.warning("[outbox] no se pudo asegurar esquema: %s", exc)

    def insert_pending(
        self,
        event_uid: str,
        camera_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Inserta una alerta pendiente. ON CONFLICT DO NOTHING → idempotente.

        Devuelve True si se insertó, False si ya existía.
        """
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO camera_alert_outbox
                            (event_uid, camera_id, event_type, telegram_payload)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (event_uid) DO NOTHING
                        """,
                        (event_uid, camera_id, event_type, Json(payload)),
                    )
                    inserted = cur.rowcount == 1
                conn.commit()
            return inserted
        except Exception as exc:
            _log.error("[outbox] error insertando alerta [%s]: %s", event_uid, exc)
            return False

    def drain(self, *, batch_size: int = 5) -> int:
        """Procesa hasta batch_size alertas pendientes. Devuelve cuántas se enviaron."""
        self.ensure_schema()
        rows = self._claim_pending(batch_size)
        sent = 0
        for row in rows:
            if self._process_row(row):
                sent += 1
        return sent

    def pending_count(self) -> int:
        """Cuenta alertas pendientes o fallidas con retry disponible ya."""
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT count(*)
                        FROM camera_alert_outbox
                        WHERE status IN ('pending','failed')
                          AND next_retry_at <= now()
                        """
                    )
                    row = cur.fetchone()
            return int((row or [0])[0])
        except Exception:
            return -1

    # ----------------------------------------------------------------- private

    def _claim_pending(self, batch_size: int) -> list[dict[str, Any]]:
        """SELECT FOR UPDATE SKIP LOCKED → marca como 'processing' atómicamente."""
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, event_uid, camera_id, event_type,
                               attempts, telegram_payload
                        FROM camera_alert_outbox
                        WHERE status IN ('pending', 'failed')
                          AND next_retry_at <= now()
                        ORDER BY created_at
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                        """,
                        (batch_size,),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
                    if rows:
                        ids = [r["id"] for r in rows]
                        cur.execute(
                            """
                            UPDATE camera_alert_outbox
                            SET status = 'processing', updated_at = now()
                            WHERE id = ANY(%s::uuid[])
                            """,
                            ([str(item) for item in ids],),
                        )
                conn.commit()
            return rows
        except Exception as exc:
            _log.error("[outbox] error reclamando filas: %s", exc)
            return []

    def _process_row(self, row: dict[str, Any]) -> bool:
        outbox_id = str(row["id"])
        event_uid = str(row.get("event_uid") or outbox_id)
        payload = row.get("telegram_payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        try:
            delivery = self._dispatch(payload)
            sent_count = int(delivery.get("sent") or 0)
            if sent_count <= 0:
                raise RuntimeError("Telegram no confirmó envío (sent=0)")
            self._mark_sent(outbox_id)
            _log.info("[outbox] alerta enviada: %s", event_uid)
            return True
        except Exception as exc:
            attempts = int(row.get("attempts") or 0) + 1
            self._mark_failed(outbox_id, str(exc)[:500], attempts)
            _log.warning("[outbox] intento %d fallido para %s: %s", attempts, event_uid, exc)
            return False

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Descarga archivo remoto si hace falta, luego envía por Telegram."""
        message = str(payload.get("message") or "")
        remote_video = str(payload.get("remote_video") or "").strip()
        remote_crop = str(payload.get("remote_crop") or "").strip()

        if remote_video:
            local = self._cache_remote_file(remote_video)
            rendered = self._render_video(local)
            return self._send_video(message, rendered)
        if remote_crop:
            local = self._cache_remote_file(remote_crop)
            return self._send_photo(message, local)
        return self._send_text(message)

    def _mark_sent(self, outbox_id: str) -> None:
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE camera_alert_outbox
                        SET status = 'sent', sent_at = now(), updated_at = now()
                        WHERE id = %s
                        """,
                        (outbox_id,),
                    )
                conn.commit()
        except Exception as exc:
            _log.error("[outbox] no se pudo marcar como enviada %s: %s", outbox_id, exc)

    def _mark_failed(self, outbox_id: str, error: str, attempts: int) -> None:
        is_dead = attempts >= _MAX_ATTEMPTS
        status = "dead_letter" if is_dead else "failed"
        backoff_idx = min(attempts - 1, len(_BACKOFF_SECONDS) - 1)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=_BACKOFF_SECONDS[backoff_idx])
        try:
            with psycopg2.connect(self._db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE camera_alert_outbox
                        SET status        = %s,
                            attempts      = %s,
                            last_error    = %s,
                            next_retry_at = %s,
                            updated_at    = now()
                        WHERE id = %s
                        """,
                        (status, attempts, error, next_retry, outbox_id),
                    )
                conn.commit()
        except Exception as exc:
            _log.error("[outbox] no se pudo marcar como fallida %s: %s", outbox_id, exc)
