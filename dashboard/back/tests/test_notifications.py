from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from back.app.services.send_telegram import normalized_chat_ids
from back.app.services.telegram_alert_worker import TelegramAlertWorker


def _worker(**overrides) -> TelegramAlertWorker:
    dependencies = {
        "send_video_fn": MagicMock(return_value={"sent": 1}),
        "send_photo_fn": MagicMock(return_value={"sent": 1}),
        "send_text_fn": MagicMock(return_value={"sent": 1}),
        "cache_remote_file_fn": MagicMock(return_value=Path("/tmp/source.media")),
        "render_video_fn": MagicMock(return_value=Path("/tmp/rendered.mp4")),
    }
    dependencies.update(overrides)
    return TelegramAlertWorker("postgresql://test", **dependencies)


class TestTelegramChatIds(unittest.TestCase):
    def test_normalized_chat_ids_strips_empty_values(self) -> None:
        self.assertEqual(normalized_chat_ids(["", " 123 ", "\n", "-456"]), ["123", "-456"])

    def test_normalized_chat_ids_requires_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "chat ID"):
            normalized_chat_ids(["", "  "])


class TestTelegramAlertWorkerDispatch(unittest.TestCase):
    def test_dispatch_prefers_video_over_photo(self) -> None:
        worker = _worker()

        result = worker._dispatch(
            {
                "message": "Alerta",
                "remote_video": "/remote/clip.mp4",
                "remote_crop": "/remote/crop.jpg",
            }
        )

        self.assertEqual(result["sent"], 1)
        worker._cache_remote_file.assert_called_once_with("/remote/clip.mp4")
        worker._render_video.assert_called_once_with(Path("/tmp/source.media"))
        worker._send_video.assert_called_once_with("Alerta", Path("/tmp/rendered.mp4"))
        worker._send_photo.assert_not_called()
        worker._send_text.assert_not_called()

    def test_dispatch_sends_photo_when_no_video(self) -> None:
        worker = _worker()

        result = worker._dispatch({"message": "Foto", "remote_crop": "/remote/crop.jpg"})

        self.assertEqual(result["sent"], 1)
        worker._cache_remote_file.assert_called_once_with("/remote/crop.jpg")
        worker._send_photo.assert_called_once_with("Foto", Path("/tmp/source.media"))
        worker._send_video.assert_not_called()
        worker._send_text.assert_not_called()

    def test_dispatch_sends_text_without_media(self) -> None:
        worker = _worker()

        result = worker._dispatch({"message": "Solo texto"})

        self.assertEqual(result["sent"], 1)
        worker._send_text.assert_called_once_with("Solo texto")
        worker._cache_remote_file.assert_not_called()
        worker._send_video.assert_not_called()
        worker._send_photo.assert_not_called()

    def test_process_row_marks_success(self) -> None:
        worker = _worker()
        worker._mark_sent = MagicMock()
        worker._mark_failed = MagicMock()

        ok = worker._process_row(
            {
                "id": "0f2be2fb-5bc7-45ad-9470-789a12345678",
                "event_uid": "uid-1",
                "attempts": 0,
                "telegram_payload": {"message": "ok"},
            }
        )

        self.assertTrue(ok)
        worker._mark_sent.assert_called_once_with("0f2be2fb-5bc7-45ad-9470-789a12345678")
        worker._mark_failed.assert_not_called()

    def test_process_row_marks_failure_with_next_attempt(self) -> None:
        worker = _worker(send_text_fn=MagicMock(side_effect=RuntimeError("timeout")))
        worker._mark_sent = MagicMock()
        worker._mark_failed = MagicMock()

        ok = worker._process_row(
            {
                "id": "0f2be2fb-5bc7-45ad-9470-789a12345678",
                "event_uid": "uid-2",
                "attempts": 2,
                "telegram_payload": {"message": "fail"},
            }
        )

        self.assertFalse(ok)
        worker._mark_sent.assert_not_called()
        worker._mark_failed.assert_called_once_with(
            "0f2be2fb-5bc7-45ad-9470-789a12345678",
            "timeout",
            3,
        )


if __name__ == "__main__":
    unittest.main()
