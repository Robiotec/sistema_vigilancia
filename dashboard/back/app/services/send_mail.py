from __future__ import annotations

import argparse
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from back.app.services.notification_settings import load_email_recipients_from_db, load_notification_settings

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enviar correo usando la configuración persistida del dashboard.")
    parser.add_argument("--sender-email", default="", help="Sobrescribe el correo emisor configurado.")
    parser.add_argument("--sender-password", default="", help="Sobrescribe la contraseña configurada.")
    parser.add_argument("--smtp-host", default="", help="Sobrescribe el servidor SMTP configurado.")
    parser.add_argument("--smtp-port", type=int, default=0, help="Sobrescribe el puerto SMTP configurado.")
    parser.add_argument("--recipient", dest="recipients", action="append", default=[], help="Agrega destinatarios.")
    parser.add_argument("--subject", default="", help="Sobrescribe el asunto configurado.")
    parser.add_argument("--message", default="", help="Sobrescribe el mensaje configurado.")
    return parser

def merged_email_settings(args: argparse.Namespace) -> dict:
    settings = load_notification_settings().get("email", {})
    recipients = [str(item).strip() for item in args.recipients if str(item).strip()] or list(settings.get("recipients") or [])
    return {
        "sender_email": (args.sender_email or settings.get("sender_email") or "").strip(),
        "sender_password": (args.sender_password or settings.get("sender_password") or "").strip(),
        "smtp_host": (args.smtp_host or settings.get("smtp_host") or "").strip(),
        "smtp_port": int(args.smtp_port or settings.get("smtp_port") or 587),
        "recipients": recipients,
        "subject": (args.subject or settings.get("subject") or "").strip(),
        "message": (args.message or settings.get("message") or "").strip(),
    }

def validate_email_settings(settings: dict) -> None:
    if not settings["sender_email"]:
        raise SystemExit("Falta el correo emisor configurado.")
    if not settings["sender_password"]:
        raise SystemExit("Falta la contraseña del correo emisor configurada.")
    if not settings["smtp_host"]:
        raise SystemExit("Falta el servidor SMTP configurado.")
    if not settings["recipients"]:
        raise SystemExit("No hay destinatarios configurados.")

def validate_email_settings_value(settings: dict) -> None:
    try:
        validate_email_settings(settings)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc

def _attachment_parts(settings: dict) -> list[MIMEBase]:
    parts: list[MIMEBase] = []
    attachments = settings.get("attachments")
    if not isinstance(attachments, list):
        return parts
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        filename = str(attachment.get("filename") or "adjunto.bin").strip() or "adjunto.bin"
        content = attachment.get("content", b"")
        if isinstance(content, str):
            payload = content.encode("utf-8")
        else:
            payload = bytes(content or b"")
        mime_type = str(attachment.get("mime_type") or "application/octet-stream")
        maintype, _, subtype = mime_type.partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(payload)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        parts.append(part)
    return parts

def send_email(settings: dict) -> list[str]:
    validate_email_settings_value(settings)
    sent: list[str] = []
    attachments = _attachment_parts(settings)

    server = smtplib.SMTP(settings["smtp_host"], settings["smtp_port"])
    try:
        server.starttls()
        server.login(settings["sender_email"], settings["sender_password"])

        for recipient in settings["recipients"]:
            msg = MIMEMultipart()
            msg["From"] = settings["sender_email"]
            msg["To"] = recipient
            msg["Subject"] = settings["subject"]
            msg.attach(MIMEText(settings["message"], "plain"))
            for part in attachments:
                msg.attach(part)
            server.sendmail(settings["sender_email"], recipient, msg.as_string())
            sent.append(recipient)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    return sent

def send_configured_email() -> list[str]:
    args = build_parser().parse_args([])
    settings = merged_email_settings(args)
    db_recipients = load_email_recipients_from_db()
    if db_recipients is not None:
        settings["recipients"] = db_recipients
    return send_email(settings)

def main() -> int:
    args = build_parser().parse_args()
    settings = merged_email_settings(args)
    try:
        sent = send_email(settings)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    for recipient in sent:
        print(f"[OK] Enviado a {recipient}")

    print("[OK] Proceso completado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
