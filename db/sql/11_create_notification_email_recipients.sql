CREATE TABLE IF NOT EXISTS notification_email_recipients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email varchar(180) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_email_recipients_email
    ON notification_email_recipients (lower(email));

CREATE INDEX IF NOT EXISTS idx_notification_email_recipients_active
    ON notification_email_recipients (active);
