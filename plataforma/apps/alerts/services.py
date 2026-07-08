from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.validators import validate_email
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone

from apps.alerts.models import CameraEventHistory, NotificationEmailRecipient, NotificationTelegramChat

DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "email": {
        "sender_email": "",
        "sender_password": "",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "subject": "Correo Informativo - Prueba de Envio",
        "message": (
            "Estimados,\n"
            "Este es un correo de prueba enviado automaticamente mediante Robiotec.\n\n"
            "Saludos cordiales."
        ),
    },
    "telegram": {
        "bot_token": "",
        "message": (
            "ALERTA\n\n"
            "Se detecto una persona en un area restringida.\n\n"
            "Ubicacion: Legemesa"
        ),
        "image_path": "/root/robiotec/plataforma/apps/frontend/static/brand/robo.png",
    },
}

EVENT_CATEGORY_LABELS = {
    "alerta": "Alerta",
    "acceso": "Acceso",
    "reconocimiento_facial": "Reconocimiento facial",
    "movimiento": "Movimiento",
    "vehiculo": "Vehiculo",
    "sistema": "Sistema",
}
EVENT_TYPE_LABELS = {
    "person": "Persona detectada",
    "plate": "Vehiculo detectado",
    "clip": "Zona detectada",
    "click": "Click detectado",
    "clips_movimiento": "Movimiento detectado",
    "clips_zona": "Alerta de zona",
}
EVENT_STATUS_VALUES = {"new", "reviewed", "archived", "dismissed"}


class AlertRecipientService:
    def active_emails(self) -> list[str]:
        NotificationChannelService.ensure_tables()
        return list(
            NotificationEmailRecipient.objects.filter(active=True)
            .order_by("email")
            .values_list("email", flat=True)
        )


class NotificationChannelService:
    def load(self, *, reveal_secrets: bool = False) -> dict[str, object]:
        self.ensure_tables()
        settings_payload = self._settings_payload()
        email = settings_payload["email"]
        telegram = settings_payload["telegram"]
        recipients = self.email_recipients()
        chat_ids = self.telegram_chat_ids()
        return {
            "email": {
                "sender_email": email.get("sender_email", ""),
                "sender_password": email.get("sender_password", "") if reveal_secrets else "",
                "has_sender_password": bool(email.get("sender_password")),
                "smtp_host": email.get("smtp_host", "smtp.office365.com"),
                "smtp_port": int(email.get("smtp_port") or 587),
                "subject": email.get("subject", ""),
                "message": email.get("message", ""),
                "recipients": recipients,
            },
            "telegram": {
                "bot_token": telegram.get("bot_token", "") if reveal_secrets else "",
                "has_bot_token": bool(telegram.get("bot_token")),
                "chat_ids": chat_ids,
                "message": telegram.get("message", ""),
                "image_path": telegram.get("image_path", ""),
            },
        }

    def save(self, payload: dict[str, object] | None) -> dict[str, object]:
        self.ensure_tables()
        source = payload if isinstance(payload, dict) else {}
        current = self._settings_payload()
        email_source = source.get("email") if isinstance(source.get("email"), dict) else {}
        telegram_source = source.get("telegram") if isinstance(source.get("telegram"), dict) else {}

        email = current["email"]
        email["sender_email"] = _clean(email_source.get("sender_email", email.get("sender_email")))
        email_password = _clean(email_source.get("sender_password"))
        if email_password:
            email["sender_password"] = email_password
        email["smtp_host"] = _clean(email_source.get("smtp_host", email.get("smtp_host"))) or "smtp.office365.com"
        email["smtp_port"] = _int_or_default(email_source.get("smtp_port", email.get("smtp_port")), 587)
        email["subject"] = _clean(email_source.get("subject", email.get("subject")))
        email["message"] = str(email_source.get("message", email.get("message")) or "").strip()

        recipients = _normalize_emails(email_source.get("recipients", self.email_recipients()))
        if recipients:
            self.replace_email_recipients(recipients)

        telegram = current["telegram"]
        token = _clean(telegram_source.get("bot_token"))
        if token:
            telegram["bot_token"] = token
        telegram["message"] = str(telegram_source.get("message", telegram.get("message")) or "").strip()
        telegram["image_path"] = _clean(telegram_source.get("image_path", telegram.get("image_path")))
        chat_ids = _normalize_lines(telegram_source.get("chat_ids", self.telegram_chat_ids()))
        if chat_ids:
            self.replace_telegram_chat_ids(chat_ids)

        self._write_settings(current)
        return self.load()

    def email_recipients(self) -> list[str]:
        self.ensure_tables()
        return list(
            NotificationEmailRecipient.objects.filter(active=True)
            .order_by("email")
            .values_list("email", flat=True)
        )

    def add_email_recipient(self, email: str) -> list[str]:
        self.ensure_tables()
        normalized = _normalize_emails([email])
        if not normalized:
            raise ValueError("Ingresa un correo valido.")
        recipient = normalized[0]
        existing = NotificationEmailRecipient.objects.filter(email__iexact=recipient).first()
        if existing:
            existing.email = recipient
            existing.active = True
            existing.updated_at = timezone.now()
            existing.save(update_fields=["email", "active", "updated_at"])
        else:
            NotificationEmailRecipient.objects.create(
                email=recipient,
                active=True,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
        return self.email_recipients()

    def remove_email_recipient(self, email: str) -> list[str]:
        self.ensure_tables()
        recipient = _clean(email)
        if not recipient:
            raise ValueError("Ingresa un correo valido.")
        NotificationEmailRecipient.objects.filter(email__iexact=recipient).delete()
        return self.email_recipients()

    def replace_email_recipients(self, recipients: list[str]) -> list[str]:
        self.ensure_tables()
        normalized = _normalize_emails(recipients)
        NotificationEmailRecipient.objects.update(active=False, updated_at=timezone.now())
        for recipient in normalized:
            self.add_email_recipient(recipient)
        return self.email_recipients()

    def telegram_chat_ids(self) -> list[str]:
        self.ensure_tables()
        return list(
            NotificationTelegramChat.objects.filter(active=True)
            .order_by("chat_id")
            .values_list("chat_id", flat=True)
        )

    def add_telegram_chat_id(self, chat_id: str) -> list[str]:
        self.ensure_tables()
        normalized = _normalize_lines([chat_id])
        if not normalized:
            raise ValueError("Ingresa un ID de Telegram valido.")
        value = normalized[0]
        existing = NotificationTelegramChat.objects.filter(chat_id=value).first()
        if existing:
            existing.active = True
            existing.updated_at = timezone.now()
            existing.save(update_fields=["active", "updated_at"])
        else:
            NotificationTelegramChat.objects.create(
                chat_id=value,
                active=True,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
        return self.telegram_chat_ids()

    def remove_telegram_chat_id(self, chat_id: str) -> list[str]:
        self.ensure_tables()
        value = _clean(chat_id)
        if not value:
            raise ValueError("Ingresa un ID de Telegram valido.")
        NotificationTelegramChat.objects.filter(chat_id=value).delete()
        return self.telegram_chat_ids()

    def replace_telegram_chat_ids(self, chat_ids: list[str]) -> list[str]:
        self.ensure_tables()
        normalized = _normalize_lines(chat_ids)
        NotificationTelegramChat.objects.update(active=False, updated_at=timezone.now())
        for chat_id in normalized:
            self.add_telegram_chat_id(chat_id)
        return self.telegram_chat_ids()

    def send_test_email(self) -> dict[str, object]:
        from apps.reports.services import EmailSender

        payload = self.load(reveal_secrets=True)
        email = payload["email"] if isinstance(payload.get("email"), dict) else {}
        sent = EmailSender().send(
            {
                "sender_email": email.get("sender_email"),
                "sender_password": email.get("sender_password"),
                "smtp_host": email.get("smtp_host"),
                "smtp_port": email.get("smtp_port"),
                "recipients": email.get("recipients"),
                "subject": email.get("subject"),
                "message": email.get("message"),
            }
        )
        return {"ok": True, "sent": sent, "total": len(sent)}

    def send_test_telegram(self, *, timeout: float = 20.0) -> dict[str, object]:
        payload = self.load(reveal_secrets=True)
        telegram = payload["telegram"] if isinstance(payload.get("telegram"), dict) else {}
        token = _clean(telegram.get("bot_token"))
        if not token or ":" not in token:
            raise ValueError("Falta el token del bot de Telegram o no parece valido.")
        chat_ids = _normalize_lines(telegram.get("chat_ids"))
        if not chat_ids:
            raise ValueError("No hay chat ID de Telegram configurado.")
        message = _clean(telegram.get("message")) or "Prueba de notificacion Robiotec."
        results = []
        sent = 0
        for chat_id in chat_ids:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": message},
                timeout=timeout,
            )
            try:
                body = response.json()
            except ValueError:
                body = {"ok": False, "description": response.text}
            ok = response.status_code == 200 and bool(body.get("ok"))
            if ok:
                sent += 1
            results.append({"chat_id": chat_id, "ok": ok, "detail": body.get("description") or "OK"})
        return {"ok": sent > 0, "sent": sent, "total": len(chat_ids), "results": results}

    def _settings_payload(self) -> dict[str, Any]:
        payload = copy.deepcopy(DEFAULT_NOTIFICATION_SETTINGS)
        path = self._settings_path()
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw.get("email"), dict):
                payload["email"].update(raw["email"])
            if isinstance(raw.get("telegram"), dict):
                payload["telegram"].update(raw["telegram"])
        if not payload["email"].get("sender_password"):
            payload["email"]["sender_password"] = _clean(getattr(settings, "ROBIOTEC_SMTP_PASSWORD", ""))
        return payload

    def _write_settings(self, payload: dict[str, object]) -> None:
        path = self._settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _settings_path() -> Path:
        return Path(
            getattr(
                settings,
                "ROBIOTEC_NOTIFICATION_SETTINGS_PATH",
                settings.BASE_DIR / "data" / "notification_settings.json",
            )
        )

    @staticmethod
    def ensure_tables() -> None:
        existing = set(connection.introspection.table_names())
        models = [NotificationEmailRecipient, NotificationTelegramChat]
        missing = [model for model in models if model._meta.db_table not in existing]
        if not missing:
            return
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
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
                    """
                )
            return
        with connection.schema_editor() as schema_editor:
            for model in missing:
                schema_editor.create_model(model)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_lines(value: object) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[\n,;]+", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean(item)
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    return normalized


def _normalize_emails(value: object) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in _normalize_lines(value):
        try:
            validate_email(item)
        except Exception:
            continue
        key = item.lower()
        if key not in seen:
            normalized.append(item)
            seen.add(key)
    return normalized


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


class EventHistoryService:
    allowed_categories = {"alerta", "acceso", "reconocimiento_facial", "movimiento", "vehiculo", "sistema"}
    allowed_event_types = {"person", "plate", "clip", "click", "clips_movimiento", "clips_zona"}
    allowed_origins = {"fixed_camera", "vehicle", "drone", "system"}

    def list(self, filters: dict[str, object] | None = None) -> dict[str, object]:
        source = filters if isinstance(filters, dict) else {}
        page = max(1, _int_or_default(source.get("page"), 1))
        page_size = max(1, min(_int_or_default(source.get("page_size"), 12), 50))
        queryset = self._filtered_queryset(source)
        total = queryset.count()
        offset = (page - 1) * page_size
        items = [
            self._item(row)
            for row in queryset.order_by("-detected_at", "-created_at")[offset : offset + page_size]
        ]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def filter_options(self, field: str) -> dict[str, object]:
        normalized = str(field or "").strip().lower()
        if normalized not in {"camera_id", "camera_name"}:
            raise ValueError("Filtro no permitido")
        rows = (
            CameraEventHistory.objects.exclude(**{f"{normalized}__isnull": True})
            .exclude(**{normalized: ""})
            .values(normalized)
            .annotate(total=Count("id"))
            .order_by(normalized)
        )
        items = [
            {
                "value": str(row.get(normalized) or ""),
                "label": str(row.get(normalized) or ""),
                "count": int(row.get("total") or 0),
            }
            for row in rows
            if str(row.get(normalized) or "").strip()
        ]
        return {"items": items, "total": len(items)}

    def update_status(self, event_id: str, status: str) -> dict[str, object]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in EVENT_STATUS_VALUES:
            raise ValueError("Estado no permitido")
        event = CameraEventHistory.objects.filter(id=event_id).first()
        if event is None:
            raise FileNotFoundError("Evento no encontrado")
        event.status = normalized_status
        event.updated_at = timezone.now()
        event.save(update_fields=["status", "updated_at"])
        return {"id": str(event.id), "status": event.status}

    def serialize(self, event: CameraEventHistory) -> dict[str, object]:
        return self._item(event)

    def _filtered_queryset(self, filters: dict[str, object]):
        queryset = CameraEventHistory.objects.all()
        query = _clean(filters.get("q") or filters.get("query"))
        if query:
            queryset = queryset.filter(
                Q(camera_id__icontains=query)
                | Q(camera_name__icontains=query)
                | Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(person_name__icontains=query)
                | Q(person_id__icontains=query)
                | Q(plate__icontains=query)
            )
        date_from = _clean(filters.get("date_from"))
        if date_from:
            queryset = queryset.filter(detected_at__date__gte=date_from)
        date_to = _clean(filters.get("date_to"))
        if date_to:
            queryset = queryset.filter(detected_at__date__lte=date_to)
        time_from = _clean(filters.get("time_from"))
        if time_from:
            queryset = queryset.filter(detected_at__time__gte=time_from)
        time_to = _clean(filters.get("time_to"))
        if time_to:
            queryset = queryset.filter(detected_at__time__lte=time_to)
        camera_id = _clean(filters.get("camera_id"))
        if camera_id:
            queryset = queryset.filter(camera_id=camera_id)
        camera_name = _clean(filters.get("camera_name"))
        if camera_name:
            queryset = queryset.filter(camera_name=camera_name)
        queryset = self._filter_csv(queryset, "event_category", filters.get("categories"), self.allowed_categories)
        queryset = self._filter_csv(queryset, "event_type", filters.get("event_types"), self.allowed_event_types)
        queryset = self._filter_csv(queryset, "origin", filters.get("origins"), self.allowed_origins)
        queryset = self._filter_csv(queryset, "status", filters.get("statuses"), EVENT_STATUS_VALUES)
        return queryset

    @staticmethod
    def _filter_csv(queryset, field: str, raw: object, allowed: set[str]):
        raw_text = _clean(raw)
        if not raw_text:
            return queryset
        values = []
        for value in raw_text.split(","):
            normalized = value.strip().lower()
            if normalized == "__none__":
                return queryset.none()
            if normalized in allowed and normalized not in values:
                values.append(normalized)
        return queryset.filter(**{f"{field}__in": values}) if values else queryset.none()

    def _item(self, event: CameraEventHistory) -> dict[str, object]:
        payload = event.detail_payload if isinstance(event.detail_payload, dict) else {}
        return {
            "id": str(event.id),
            "event_type": event.event_type,
            "event_type_label": EVENT_TYPE_LABELS.get(str(event.event_type or ""), event.event_type),
            "event_category": event.event_category,
            "event_category_label": EVENT_CATEGORY_LABELS.get(str(event.event_category or ""), event.event_category),
            "origin": event.origin,
            "camera_id": event.camera_id,
            "camera_name": event.camera_name or event.camera_id,
            "camera_location": event.camera_location,
            "event_timestamp": event.event_timestamp,
            "detected_at": event.detected_at.isoformat() if event.detected_at else "",
            "detected_date": event.detected_date.isoformat() if event.detected_date else "",
            "title": event.title,
            "description": event.description,
            "person_id": event.person_id,
            "person_name": event.person_name,
            "plate": event.plate,
            "track_id": event.track_id,
            "status": event.status,
            "severity": event.severity,
            "json_file_path": event.json_file_path,
            "video_file_path": event.video_file_path,
            "image_file_path": event.image_file_path,
            "crop_path": event.crop_path,
            "detail_payload": payload,
            "primary": self._primary(event),
            "summary": self._summary(event),
        }

    @staticmethod
    def _primary(event: CameraEventHistory) -> str:
        if event.plate:
            return event.plate
        if event.person_name:
            return event.person_name
        if event.person_id:
            return f"Persona {event.person_id}"
        return event.title or "Evento detectado"

    @staticmethod
    def _summary(event: CameraEventHistory) -> str:
        camera = event.camera_name or event.camera_id or "Sin camara"
        value = event.plate or event.person_name or event.person_id or event.description or event.title or "Sin detalle"
        label = EVENT_TYPE_LABELS.get(str(event.event_type or ""), event.event_type or "Evento")
        return f"Camara: {camera} | Tipo: {label} | Deteccion: {value}"
