from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "notification_settings.json"

EMAIL_RECIPIENTS_TABLE_SQL = """
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
"""

DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "email": {
        "sender_email": "robiotec@grupominerobonanza.com",
        "sender_password": "Bonanz@2024",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "recipients": [
            "yuchuari@grupominerobonanza.com",
            "pclemente@grupominerobonanza.com",
            "dguevara@grupominerobonanza.com",
        ],
        "subject": "Correo Informativo - Prueba de Envío",
        "message": (
            "Estimados,\n"
            "Este es un correo de prueba enviado automáticamente mediante Python.\n\n"
            "Saludos cordiales."
        ),
    },
    "telegram": {
        "bot_token": "8593701119:AAHJ0kb86mizOYxuyEInl9Xy4ylNTgk1Qts",
        "chat_ids": ["-1003416074376"],
        "message": (
            "ALERTA\n\n"
            "Se detecto una persona en un area restringida.\n\n"
            "Ubicacion: Legemesa\n"
            "Hora: 14:35:22"
        ),
        "image_path": "/home/pedro/Documentos/sistema_vigilancia/dashboard/front/static/assets/robo.png",
    },
}


def _normalized_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, list):
        items = value
    else:
        items = []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized


def _deep_defaults() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_NOTIFICATION_SETTINGS)


def _db_execute(query: str, params: tuple[Any, ...] | None = None) -> None:
    from back.app.services.conection_sql_postgrest import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
    finally:
        conn.close()


def _db_fetch_email_recipients() -> list[str]:
    from back.app.services.conection_sql_postgrest import fetch_all

    try:
        rows = fetch_all(
            """
            SELECT email
            FROM notification_email_recipients
            WHERE active = true
            ORDER BY lower(email)
            """
        )
    except Exception:
        rows = fetch_all(
            """
            SELECT email
            FROM notification_email_recipients
            ORDER BY lower(email)
            """
        )
    return _normalized_lines([row.get("email") for row in rows])


def ensure_email_recipients_table() -> None:
    _db_execute(EMAIL_RECIPIENTS_TABLE_SQL)


def load_email_recipients_from_db(seed_recipients: list[str] | None = None) -> list[str] | None:
    try:
        try:
            recipients = _db_fetch_email_recipients()
        except Exception:
            ensure_email_recipients_table()
            recipients = _db_fetch_email_recipients()
        seed = _normalized_lines(seed_recipients or [])
        if not recipients and seed:
            save_email_recipients_to_db(seed)
            return _db_fetch_email_recipients()
        return recipients
    except Exception:
        return None


def save_email_recipients_to_db(recipients: list[str]) -> None:
    normalized = _normalized_lines(recipients)
    ensure_email_recipients_table()
    try:
        _db_execute("UPDATE notification_email_recipients SET active = false, updated_at = now()")
    except Exception:
        _db_execute("DELETE FROM notification_email_recipients")
        for recipient in normalized:
            _db_execute("INSERT INTO notification_email_recipients (email) VALUES (%s)", (recipient,))
        return
    for recipient in normalized:
        _db_execute(
            """
            INSERT INTO notification_email_recipients (email, active)
            VALUES (%s, true)
            ON CONFLICT ((lower(email)))
            DO UPDATE SET active = true, updated_at = now()
            """,
            (recipient,),
        )


def add_email_recipient_to_db(email: str) -> list[str]:
    normalized = _normalized_lines([email])
    if not normalized:
        raise ValueError("Ingresa un correo valido.")
    recipient = normalized[0]
    ensure_email_recipients_table()
    try:
        _db_execute(
            """
            INSERT INTO notification_email_recipients (email, active)
            VALUES (%s, true)
            ON CONFLICT ((lower(email)))
            DO UPDATE SET active = true, updated_at = now()
            """,
            (recipient,),
        )
    except Exception:
        _db_execute(
            """
            INSERT INTO notification_email_recipients (email)
            SELECT %s
            WHERE NOT EXISTS (
                SELECT 1
                FROM notification_email_recipients
                WHERE lower(email) = lower(%s)
            )
            """,
            (recipient, recipient),
        )
    return _db_fetch_email_recipients()


def remove_email_recipient_from_db(email: str) -> list[str]:
    normalized = _normalized_lines([email])
    if not normalized:
        raise ValueError("Ingresa un correo valido.")
    recipient = normalized[0]
    ensure_email_recipients_table()
    _db_execute(
        "DELETE FROM notification_email_recipients WHERE lower(email) = lower(%s)",
        (recipient,),
    )
    return _db_fetch_email_recipients()


def normalize_notification_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _deep_defaults()
    source = payload if isinstance(payload, dict) else {}

    email_source = source.get("email") if isinstance(source.get("email"), dict) else {}
    telegram_source = source.get("telegram") if isinstance(source.get("telegram"), dict) else {}

    normalized["email"]["sender_email"] = str(
        email_source.get("sender_email", normalized["email"]["sender_email"])
    ).strip()
    normalized["email"]["sender_password"] = str(
        email_source.get("sender_password", normalized["email"]["sender_password"])
    ).strip()
    normalized["email"]["smtp_host"] = str(
        email_source.get("smtp_host", normalized["email"]["smtp_host"])
    ).strip()
    try:
        normalized["email"]["smtp_port"] = int(email_source.get("smtp_port", normalized["email"]["smtp_port"]))
    except (TypeError, ValueError):
        normalized["email"]["smtp_port"] = DEFAULT_NOTIFICATION_SETTINGS["email"]["smtp_port"]
    normalized["email"]["recipients"] = _normalized_lines(
        email_source.get("recipients", normalized["email"]["recipients"])
    )
    normalized["email"]["subject"] = str(email_source.get("subject", normalized["email"]["subject"])).strip()
    normalized["email"]["message"] = str(email_source.get("message", normalized["email"]["message"])).strip()

    normalized["telegram"]["bot_token"] = str(
        telegram_source.get("bot_token", normalized["telegram"]["bot_token"])
    ).strip()
    normalized["telegram"]["chat_ids"] = _normalized_lines(
        telegram_source.get("chat_ids", normalized["telegram"]["chat_ids"])
    )
    normalized["telegram"]["message"] = str(
        telegram_source.get("message", normalized["telegram"]["message"])
    ).strip()
    normalized["telegram"]["image_path"] = str(
        telegram_source.get("image_path", normalized["telegram"]["image_path"])
    ).strip()

    return normalized


def load_notification_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        settings = _deep_defaults()
        db_recipients = load_email_recipients_from_db(settings["email"]["recipients"])
        if db_recipients is not None:
            settings["email"]["recipients"] = db_recipients
        return settings
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        settings = _deep_defaults()
    else:
        settings = normalize_notification_settings(payload)
    db_recipients = load_email_recipients_from_db(settings["email"]["recipients"])
    if db_recipients is not None:
        settings["email"]["recipients"] = db_recipients
    return settings


def save_notification_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_notification_settings(payload)
    try:
        save_email_recipients_to_db(normalized["email"]["recipients"])
    except Exception:
        pass
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized
