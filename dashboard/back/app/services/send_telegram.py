from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests

from back.app.services.notification_settings import load_notification_settings

DEFAULT_BOT_TOKEN = "8593701119:AAHJ0kb86mizOYxuyEInl9Xy4ylNTgk1Qts"
DEFAULT_CHAT_IDS = ["-1003416074376"]
DEFAULT_MESSAGE = """
ALERTA

Se detecto una persona en un area restringida.

Ubicacion: Legemesa
Hora: 14:35:22
""".strip()
DEFAULT_IMAGE_PATH = Path(
    "/home/pedro/Documentos/sistema_vigilancia/dashboard/front/static/assets/robo.png"
)
TELEGRAM_API_BASE = "https://api.telegram.org"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enviar una alerta con foto por Telegram.")
    parser.add_argument(
        "--token",
        default=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        help="Token del bot de Telegram. Tambien puede venir desde TELEGRAM_BOT_TOKEN.",
    )
    parser.add_argument(
        "--chat-id",
        dest="chat_ids",
        action="append",
        default=[],
        help="Chat ID destino. Puedes repetir --chat-id varias veces.",
    )
    parser.add_argument(
        "--message",
        default="",
        help="Mensaje o caption que acompana la imagen.",
    )
    parser.add_argument(
        "--image",
        default="",
        help="Ruta de la imagen que se enviara.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Timeout HTTP en segundos.",
    )
    return parser


def normalized_chat_ids(raw_chat_ids: list[str]) -> list[str]:
    resolved = [str(item).strip() for item in raw_chat_ids if str(item).strip()]
    return resolved or list(DEFAULT_CHAT_IDS)


def configured_telegram_settings() -> dict:
    return load_notification_settings().get("telegram", {})


def validate_token(token: str) -> str:
    cleaned = str(token or "").strip()
    if not cleaned or cleaned.upper() == "TU_TOKEN":
        raise SystemExit(
            "Falta el token del bot. Define TELEGRAM_BOT_TOKEN o ejecuta con "
            "--token '123456:ABC...'."
        )
    if ":" not in cleaned:
        raise SystemExit("El token del bot no parece valido. Debe tener el formato '123456:ABC...'.")
    return cleaned


def api_url(token: str, method: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{token}/{method}"


def check_bot(token: str, timeout: float) -> dict:
    response = requests.get(api_url(token, "getMe"), timeout=timeout)
    try:
      payload = response.json()
    except ValueError:
      raise SystemExit(f"No se pudo validar el bot en Telegram: HTTP {response.status_code} {response.text}")
    if response.status_code != 200 or not payload.get("ok"):
        description = payload.get("description") or response.text or "Error desconocido"
        raise SystemExit(f"Token de Telegram invalido o bot no accesible: {description}")
    return payload.get("result") or {}


def send_photo(token: str, chat_id: str, message: str, image_path: Path, timeout: float) -> tuple[bool, str]:
    with image_path.open("rb") as photo:
        response = requests.post(
            api_url(token, "sendPhoto"),
            data={"chat_id": chat_id, "caption": message},
            files={"photo": photo},
            timeout=timeout,
        )
    try:
        payload = response.json()
    except ValueError:
        return False, f"HTTP {response.status_code}: {response.text}"

    if response.status_code == 200 and payload.get("ok"):
        return True, "Enviado correctamente"

    description = payload.get("description") or response.text or "Error desconocido"
    return False, description


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = configured_telegram_settings()

    token = validate_token(args.token or settings.get("bot_token") or DEFAULT_BOT_TOKEN)
    chat_ids = normalized_chat_ids(args.chat_ids or list(settings.get("chat_ids") or []))
    message = str(args.message or settings.get("message") or DEFAULT_MESSAGE).strip()
    image_path = Path(args.image or settings.get("image_path") or str(DEFAULT_IMAGE_PATH)).expanduser().resolve()

    if not image_path.is_file():
        raise SystemExit(f"No existe la imagen a enviar: {image_path}")

    bot_info = check_bot(token, args.timeout)
    print(f"[OK] Bot validado: @{bot_info.get('username', 'sin_username')}")

    status = 0
    for chat_id in chat_ids:
        ok, detail = send_photo(token, chat_id, message, image_path, args.timeout)
        if ok:
            print(f"[OK] Enviado a {chat_id}")
        else:
            status = 1
            print(f"[ERROR] No se pudo enviar a {chat_id}: {detail}")

    return status


if __name__ == "__main__":
    raise SystemExit(main())
