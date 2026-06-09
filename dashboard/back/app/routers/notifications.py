"""Router de configuración de notificaciones (email + Telegram)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from back.app.context import _text, auth_json_response, get_token
from back.app.services.notification_settings import (
    add_email_recipient_to_db,
    add_telegram_chat_id_to_db,
    load_email_recipients_from_db,
    load_notification_settings,
    load_telegram_chat_ids_from_db,
    remove_email_recipient_from_db,
    remove_telegram_chat_id_from_db,
    save_notification_settings,
)
from back.app.services.send_mail import send_configured_email
from back.app.services.send_telegram import send_configured_telegram_alert
from back.app import application as _app_module

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notification-settings")
def notification_settings_get(request: Request):
    token = get_token(request)
    if not token:
        return auth_json_response()
    payload = load_notification_settings()
    if isinstance(payload.get("telegram"), dict):
        payload["telegram"]["bot_token"] = ""
    return payload


@router.put("/notification-settings")
async def notification_settings_update(request: Request):
    token = get_token(request)
    if not token:
        return auth_json_response()
    payload = await request.json()
    saved = save_notification_settings(payload if isinstance(payload, dict) else {})
    if isinstance(saved.get("telegram"), dict):
        saved["telegram"]["bot_token"] = ""
    return {"ok": True, "settings": saved}


# --- Email recipients ---

@router.get("/notification-email-recipients")
def notification_email_recipients_get(request: Request):
    if not get_token(request):
        return auth_json_response()
    recipients = load_email_recipients_from_db()
    if recipients is None:
        return JSONResponse({"ok": False, "error": "No se pudieron leer los correos desde PostgreSQL."}, status_code=502)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@router.post("/notification-email-recipients")
async def notification_email_recipient_create(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = add_email_recipient_to_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo agregar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@router.post("/notification-email-recipients/form")
def notification_email_recipient_create_form(request: Request, email: str = Form("")):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        add_email_recipient_to_db(email)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.delete("/notification-email-recipients")
async def notification_email_recipient_delete(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = remove_email_recipient_from_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@router.post("/notification-email-recipients/delete")
async def notification_email_recipient_delete_post(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    email = _text(payload.get("email") if isinstance(payload, dict) else "")
    try:
        recipients = remove_email_recipient_from_db(email)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el correo.")}, status_code=400)
    return {"ok": True, "recipients": recipients, "total": len(recipients)}


@router.post("/notification-email-recipients/delete-form")
def notification_email_recipient_delete_form(request: Request, email: str = Form("")):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        remove_email_recipient_from_db(email)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


# --- Telegram chat IDs ---

@router.get("/notification-telegram-chat-ids")
def notification_telegram_chat_ids_get(request: Request):
    if not get_token(request):
        return auth_json_response()
    chat_ids = load_telegram_chat_ids_from_db()
    if chat_ids is None:
        return JSONResponse({"ok": False, "error": "No se pudieron leer los IDs de Telegram desde PostgreSQL."}, status_code=502)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@router.post("/notification-telegram-chat-ids")
async def notification_telegram_chat_id_create(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = add_telegram_chat_id_to_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo agregar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@router.post("/notification-telegram-chat-ids/form")
def notification_telegram_chat_id_create_form(request: Request, chat_id: str = Form("")):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        add_telegram_chat_id_to_db(chat_id)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.delete("/notification-telegram-chat-ids")
async def notification_telegram_chat_id_delete(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = remove_telegram_chat_id_from_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@router.post("/notification-telegram-chat-ids/delete")
async def notification_telegram_chat_id_delete_post(request: Request):
    if not get_token(request):
        return auth_json_response()
    payload = await request.json()
    chat_id = _text(payload.get("chat_id") if isinstance(payload, dict) else "")
    try:
        chat_ids = remove_telegram_chat_id_from_db(chat_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": _text(exc, "No se pudo quitar el ID de Telegram.")}, status_code=400)
    return {"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)}


@router.post("/notification-telegram-chat-ids/delete-form")
def notification_telegram_chat_id_delete_form(request: Request, chat_id: str = Form("")):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        remove_telegram_chat_id_from_db(chat_id)
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


# --- Test endpoints ---

@router.post("/notification-settings/test-email")
def notification_settings_test_email(request: Request):
    if not get_token(request):
        return auth_json_response()
    try:
        sent = send_configured_email()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, "sent": sent, "total": len(sent)}


@router.post("/notification-settings/test-email-form")
def notification_settings_test_email_form(request: Request):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        send_configured_email()
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.post("/notification-settings/test-telegram")
def notification_settings_test_telegram(request: Request):
    if not get_token(request):
        return auth_json_response()
    try:
        delivery = send_configured_telegram_alert()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, **delivery}


@router.post("/notification-settings/test-telegram-form")
def notification_settings_test_telegram_form(request: Request):
    if not get_token(request):
        return RedirectResponse("/login", status_code=303)
    try:
        send_configured_telegram_alert()
    except Exception:
        pass
    return RedirectResponse("/notificaciones", status_code=303)


@router.get("/notification-settings/clip-notifier-status")
def notification_settings_clip_notifier_status(request: Request):
    if not get_token(request):
        return auth_json_response()
    feeder = _app_module._telegram_feeder
    return {"ok": True, **(feeder.status() if feeder else {"running": False})}


@router.post("/notification-settings/clip-notifier-check")
def notification_settings_clip_notifier_check(request: Request):
    if not get_token(request):
        return auth_json_response()
    feeder = _app_module._telegram_feeder
    if not feeder:
        return JSONResponse({"ok": False, "error": "Feeder no iniciado"}, status_code=503)
    try:
        result = feeder.check_once()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    return {"ok": True, **result, "status": feeder.status()}
