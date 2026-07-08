from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path

from django.test import override_settings

from apps.alerts.models import NotificationEmailRecipient, NotificationTelegramChat
from apps.alerts.services import NotificationChannelService
from apps.core.tests.legacy_schema import LegacySchemaTestCase


class NotificationChannelServiceTests(LegacySchemaTestCase):
    def test_recipients_are_normalized_and_deduplicated(self):
        service = NotificationChannelService()

        recipients = service.replace_email_recipients(["ops@example.com", "OPS@example.com", "bad"])
        chat_ids = service.replace_telegram_chat_ids(["123", "123", " 456 "])

        self.assertEqual(recipients, ["ops@example.com"])
        self.assertEqual(chat_ids, ["123", "456"])
        self.assertEqual(NotificationEmailRecipient.objects.filter(active=True).count(), 1)
        self.assertEqual(NotificationTelegramChat.objects.filter(active=True).count(), 2)

    def test_settings_are_sanitized_and_preserve_hidden_secrets(self):
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "notification_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "email": {
                            "sender_email": "alerts@example.com",
                            "sender_password": "smtp-secret",
                            "smtp_host": "smtp.example.com",
                            "smtp_port": 587,
                            "subject": "Actual",
                            "message": "Mensaje",
                        },
                        "telegram": {
                            "bot_token": "123:secret",
                            "message": "Telegram",
                            "image_path": "/tmp/image.png",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with override_settings(ROBIOTEC_NOTIFICATION_SETTINGS_PATH=str(settings_path)):
                service = NotificationChannelService()

                public_payload = service.load()
                saved = service.save(
                    {
                        "email": {
                            "sender_email": "alerts@example.com",
                            "sender_password": "",
                            "smtp_host": "smtp.office365.com",
                            "smtp_port": 587,
                            "subject": "Nuevo",
                            "message": "Nuevo mensaje",
                            "recipients": ["ops@example.com"],
                        },
                        "telegram": {
                            "bot_token": "",
                            "message": "Nuevo telegram",
                            "image_path": "/tmp/new.png",
                            "chat_ids": ["777"],
                        },
                    }
                )
                stored = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(public_payload["email"]["sender_password"], "")
        self.assertTrue(public_payload["email"]["has_sender_password"])
        self.assertEqual(public_payload["telegram"]["bot_token"], "")
        self.assertTrue(public_payload["telegram"]["has_bot_token"])
        self.assertEqual(saved["email"]["recipients"], ["ops@example.com"])
        self.assertEqual(saved["telegram"]["chat_ids"], ["777"])
        self.assertEqual(stored["email"]["sender_password"], "smtp-secret")
        self.assertEqual(stored["telegram"]["bot_token"], "123:secret")
