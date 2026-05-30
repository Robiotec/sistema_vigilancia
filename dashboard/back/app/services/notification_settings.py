from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "notification_settings.json"

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
        return _deep_defaults()
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _deep_defaults()
    return normalize_notification_settings(payload)


def save_notification_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_notification_settings(payload)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized
