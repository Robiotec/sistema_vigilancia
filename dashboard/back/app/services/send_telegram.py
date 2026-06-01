from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests

from back.app.services.notification_settings import load_notification_settings, load_telegram_chat_ids_from_db

DEFAULT_BOT_TOKEN = "8593701119:AAHJ0kb86mizOYxuyEInl9Xy4ylNTgk1Qts"
DEFAULT_CHAT_IDS = ["-1003416074376"]
DEFAULT_MESSAGE = """
ALERTA

Se detecto una persona en un area restringida.

Ubicacion: Legemesa
Hora: 14:35:22
""".strip()
DEFAULT_IMAGE_PATH = Path(
    "/root/robiotec/dashboard/front/static/assets/robo.png"
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


def validate_token_value(token: str) -> str:
    try:
        return validate_token(token)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc


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


def send_video(token: str, chat_id: str, message: str, video_path: Path, timeout: float) -> tuple[bool, str]:
    with video_path.open("rb") as video:
        response = requests.post(
            api_url(token, "sendVideo"),
            data={"chat_id": chat_id, "caption": message, "supports_streaming": "true"},
            files={"video": video},
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


def send_message(token: str, chat_id: str, message: str, timeout: float) -> tuple[bool, str]:
    response = requests.post(
        api_url(token, "sendMessage"),
        data={"chat_id": chat_id, "text": message},
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


def send_telegram_alert(
    *,
    token: str,
    chat_ids: list[str],
    message: str,
    image_path: Path,
    timeout: float = 20.0,
) -> dict:
    token = validate_token_value(token)
    resolved_chat_ids = normalized_chat_ids(chat_ids)

    if not image_path.is_file():
        raise ValueError(f"No existe la imagen a enviar: {image_path}")

    bot_info = check_bot(token, timeout)
    results = []
    ok_count = 0
    for chat_id in resolved_chat_ids:
        ok, detail = send_photo(token, chat_id, message, image_path, timeout)
        if ok:
            ok_count += 1
        results.append({"chat_id": chat_id, "ok": ok, "detail": detail})

    return {
        "bot": bot_info,
        "results": results,
        "sent": ok_count,
        "total": len(resolved_chat_ids),
    }


def send_telegram_video_alert(
    *,
    token: str,
    chat_ids: list[str],
    message: str,
    video_path: Path,
    timeout: float = 90.0,
) -> dict:
    token = validate_token_value(token)
    resolved_chat_ids = normalized_chat_ids(chat_ids)

    if not video_path.is_file():
        raise ValueError(f"No existe el video a enviar: {video_path}")

    bot_info = check_bot(token, timeout)
    results = []
    ok_count = 0
    for chat_id in resolved_chat_ids:
        ok, detail = send_video(token, chat_id, message, video_path, timeout)
        if ok:
            ok_count += 1
        results.append({"chat_id": chat_id, "ok": ok, "detail": detail})

    return {
        "bot": bot_info,
        "results": results,
        "sent": ok_count,
        "total": len(resolved_chat_ids),
    }


def send_telegram_text(
    *,
    token: str,
    chat_ids: list[str],
    message: str,
    timeout: float = 20.0,
) -> dict:
    token = validate_token_value(token)
    resolved_chat_ids = normalized_chat_ids(chat_ids)
    bot_info = check_bot(token, timeout)
    results = []
    ok_count = 0
    for chat_id in resolved_chat_ids:
        ok, detail = send_message(token, chat_id, message, timeout)
        if ok:
            ok_count += 1
        results.append({"chat_id": chat_id, "ok": ok, "detail": detail})

    return {
        "bot": bot_info,
        "results": results,
        "sent": ok_count,
        "total": len(resolved_chat_ids),
    }


def send_configured_telegram_alert(timeout: float = 20.0) -> dict:
    settings = configured_telegram_settings()
    token = settings.get("bot_token") or DEFAULT_BOT_TOKEN
    chat_ids = load_telegram_chat_ids_from_db() or list(settings.get("chat_ids") or [])
    message = str(settings.get("message") or DEFAULT_MESSAGE).strip()
    image_path = Path(settings.get("image_path") or str(DEFAULT_IMAGE_PATH)).expanduser().resolve()
    if not image_path.is_file():
        image_path = DEFAULT_IMAGE_PATH
    return send_telegram_alert(
        token=token,
        chat_ids=chat_ids,
        message=message,
        image_path=image_path,
        timeout=timeout,
    )


def send_configured_telegram_photo(
    *,
    message: str,
    image_path: Path,
    timeout: float = 20.0,
) -> dict:
    settings = configured_telegram_settings()
    token = settings.get("bot_token") or DEFAULT_BOT_TOKEN
    chat_ids = load_telegram_chat_ids_from_db() or list(settings.get("chat_ids") or [])
    return send_telegram_alert(
        token=token,
        chat_ids=chat_ids,
        message=message,
        image_path=image_path,
        timeout=timeout,
    )


def send_configured_telegram_video(
    *,
    message: str,
    video_path: Path,
    timeout: float = 90.0,
) -> dict:
    settings = configured_telegram_settings()
    token = settings.get("bot_token") or DEFAULT_BOT_TOKEN
    chat_ids = load_telegram_chat_ids_from_db() or list(settings.get("chat_ids") or [])
    return send_telegram_video_alert(
        token=token,
        chat_ids=chat_ids,
        message=message,
        video_path=video_path,
        timeout=timeout,
    )


def send_configured_telegram_text(
    *,
    message: str,
    timeout: float = 20.0,
) -> dict:
    settings = configured_telegram_settings()
    token = settings.get("bot_token") or DEFAULT_BOT_TOKEN
    chat_ids = load_telegram_chat_ids_from_db() or list(settings.get("chat_ids") or [])
    return send_telegram_text(
        token=token,
        chat_ids=chat_ids,
        message=message,
        timeout=timeout,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = configured_telegram_settings()

    token = args.token or settings.get("bot_token") or DEFAULT_BOT_TOKEN
    chat_ids = normalized_chat_ids(args.chat_ids or list(settings.get("chat_ids") or []))
    message = str(args.message or settings.get("message") or DEFAULT_MESSAGE).strip()
    image_path = Path(args.image or settings.get("image_path") or str(DEFAULT_IMAGE_PATH)).expanduser().resolve()

    try:
        delivery = send_telegram_alert(
            token=token,
            chat_ids=chat_ids,
            message=message,
            image_path=image_path,
            timeout=args.timeout,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    bot_info = delivery["bot"]
    print(f"[OK] Bot validado: @{bot_info.get('username', 'sin_username')}")

    status = 0
    for result in delivery["results"]:
        if result["ok"]:
            print(f"[OK] Enviado a {result['chat_id']}")
        else:
            status = 1
            print(f"[ERROR] No se pudo enviar a {result['chat_id']}: {result['detail']}")

    return status


if __name__ == "__main__":
    raise SystemExit(main())
