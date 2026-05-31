CREATE TABLE IF NOT EXISTS notification_telegram_chat_ids (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id varchar(80) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_telegram_chat_ids_chat_id
    ON notification_telegram_chat_ids (chat_id);

CREATE INDEX IF NOT EXISTS idx_notification_telegram_chat_ids_active
    ON notification_telegram_chat_ids (active);
