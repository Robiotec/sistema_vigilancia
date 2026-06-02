-- ---------------------------------------------------------------------------
-- Cursor de lectura incremental para manifests SFTP remotos.
-- Persiste el offset de bytes leídos para que reinicios no re-procesen líneas.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS remote_manifest_cursors (
    source_name    text             PRIMARY KEY,
    remote_path    text             NOT NULL,
    offset_bytes   bigint           NOT NULL DEFAULT 0,
    file_size      bigint,
    file_mtime     double precision,
    last_line_hash text,
    updated_at     timestamptz      NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON remote_manifest_cursors TO robiotec_app;

-- ---------------------------------------------------------------------------
-- Outbox transaccional para alertas Telegram pendientes.
-- Los workers usan SELECT ... FOR UPDATE SKIP LOCKED para evitar duplicados
-- incluso si uvicorn levanta múltiples workers.
-- ---------------------------------------------------------------------------
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
        status IN ('pending', 'processing', 'sent', 'failed', 'dead_letter')
    )
);

CREATE INDEX IF NOT EXISTS idx_camera_alert_outbox_status_retry
    ON camera_alert_outbox (status, next_retry_at)
    WHERE status IN ('pending', 'failed');

GRANT SELECT, INSERT, UPDATE, DELETE ON camera_alert_outbox TO robiotec_app;
