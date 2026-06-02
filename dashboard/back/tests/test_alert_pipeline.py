"""Pruebas unitarias del pipeline de alertas.

Cubren los componentes sin requerir SFTP ni PostgreSQL reales:
  - ManifestSFTPReader: offset, truncado, líneas parciales
  - _parse_clip_rows / _resolve_remote_path del notificador
  - TelegramAlertWorker: backoff, dead_letter, dispatch
  - Deduplicación de event_uid en outbox (ON CONFLICT semántico)

Para ejecutar:
    python -m pytest dashboard/back/tests/test_alert_pipeline.py -v

Lo que NO se puede probar sin entorno:
  - Conexión SFTP real (SSH_EVENTS_HOST)
  - Inserción en PostgreSQL (DATABASE_URL)
  - Envío real a Telegram (TELEGRAM_BOT_TOKEN)
"""
from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    from types import SimpleNamespace
    defaults = dict(
        ssh_events_host="host",
        ssh_events_user="user",
        ssh_events_password="pass",
        ssh_events_port=22,
        ssh_events_base_path="/base",
        ssh_known_hosts_path="",
        ssh_key_path="",
        database_url="postgresql://user:pass@localhost/db",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_sftp_mock(content: bytes, size: int | None = None, mtime: float = 1.0):
    """Construye un mock de SFTPClient para los tests del reader."""
    stat_result = MagicMock()
    stat_result.st_size = size if size is not None else len(content)
    stat_result.st_mtime = mtime

    file_mock = MagicMock()
    file_mock.__enter__ = lambda s: s
    file_mock.__exit__ = MagicMock(return_value=False)

    buf = io.BytesIO(content)
    file_mock.seek = buf.seek
    file_mock.read = buf.read

    sftp = MagicMock()
    sftp.stat.return_value = stat_result
    sftp.open.return_value = file_mock
    return sftp


# ---------------------------------------------------------------------------
# Tests de ManifestSFTPReader (sin DB real — mock de _db)
# ---------------------------------------------------------------------------

class TestManifestReaderOffsets(unittest.TestCase):

    def _make_reader(self, initial_offset: int = 0):
        from back.app.services.manifest_sftp_reader import ManifestSFTPReader
        settings = _make_settings()
        reader = ManifestSFTPReader(settings, "test", "/base/manifest.jsonl")
        reader._ensure_schema = MagicMock()

        saved_cursor = {
            "source_name": "test",
            "remote_path": "/base/manifest.jsonl",
            "offset_bytes": initial_offset,
            "file_size": None,
            "file_mtime": None,
            "last_line_hash": "",
        }
        reader._load_cursor = MagicMock(return_value=dict(saved_cursor))
        reader._save_cursor = MagicMock()
        return reader

    def test_reads_full_file_from_offset_zero(self):
        from back.app.services.manifest_sftp_reader import ManifestSFTPReader
        lines = [
            json.dumps({"type": "clip", "cam_id": "cam1", "ts": 1000}),
            json.dumps({"type": "person", "cam_id": "cam1", "ts": 1001}),
        ]
        content = ("\n".join(lines) + "\n").encode()
        sftp = _make_sftp_mock(content)

        reader = self._make_reader(initial_offset=0)
        rows, new_cursor = reader.read_new_lines(sftp)

        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(new_cursor)
        self.assertEqual(new_cursor["offset_bytes"], len(content))

    def test_reads_only_new_lines_since_offset(self):
        line1 = json.dumps({"type": "clip", "cam_id": "cam1", "ts": 1000}) + "\n"
        line2 = json.dumps({"type": "clip", "cam_id": "cam1", "ts": 2000}) + "\n"
        content = (line1 + line2).encode()
        first_offset = len(line1.encode())

        sftp = _make_sftp_mock(content)
        reader = self._make_reader(initial_offset=first_offset)
        rows, new_cursor = reader.read_new_lines(sftp)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ts"], 2000)
        self.assertEqual(new_cursor["offset_bytes"], len(content))

    def test_truncation_resets_offset(self):
        old_content_size = 500
        new_content = (json.dumps({"type": "clip", "cam_id": "cam1", "ts": 9000}) + "\n").encode()

        sftp = _make_sftp_mock(new_content, size=len(new_content))
        reader = self._make_reader(initial_offset=old_content_size)
        rows, new_cursor = reader.read_new_lines(sftp)

        # El offset anterior era mayor que el tamaño actual → se reinicia a 0
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ts"], 9000)
        self.assertIsNotNone(new_cursor)
        self.assertEqual(new_cursor["offset_bytes"], len(new_content))

    def test_partial_line_at_end_not_processed(self):
        # Línea completa + línea parcial (sin \n al final)
        complete = json.dumps({"type": "clip", "cam_id": "cam1", "ts": 111}) + "\n"
        partial = '{"type": "clip", "cam_id":'
        content = (complete + partial).encode()

        sftp = _make_sftp_mock(content)
        reader = self._make_reader(initial_offset=0)
        rows, new_cursor = reader.read_new_lines(sftp)

        # Solo la línea completa debe procesarse
        self.assertEqual(len(rows), 1)
        # El offset debe avanzar solo hasta el final de la línea completa
        self.assertEqual(new_cursor["offset_bytes"], len(complete.encode()))

    def test_empty_file_returns_nothing(self):
        sftp = _make_sftp_mock(b"")
        reader = self._make_reader(initial_offset=0)
        rows, new_cursor = reader.read_new_lines(sftp)
        self.assertEqual(rows, [])
        self.assertIsNone(new_cursor)

    def test_no_new_data_returns_nothing(self):
        content = (json.dumps({"type": "clip"}) + "\n").encode()
        sftp = _make_sftp_mock(content)
        # offset ya está en EOF
        reader = self._make_reader(initial_offset=len(content))
        rows, new_cursor = reader.read_new_lines(sftp)
        self.assertEqual(rows, [])
        self.assertIsNone(new_cursor)

    def test_invalid_json_lines_are_skipped(self):
        lines = [
            "this is not json\n",
            json.dumps({"type": "clip", "cam_id": "cam1", "ts": 1}) + "\n",
            "{broken\n",
        ]
        content = "".join(lines).encode()
        sftp = _make_sftp_mock(content)
        reader = self._make_reader(initial_offset=0)
        rows, _ = reader.read_new_lines(sftp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ts"], 1)

    def test_save_cursor_called_with_correct_offset(self):
        line = json.dumps({"type": "clip", "cam_id": "c", "ts": 1}) + "\n"
        content = line.encode()
        sftp = _make_sftp_mock(content)

        reader = self._make_reader(initial_offset=0)
        rows, new_cursor = reader.read_new_lines(sftp)

        # save_cursor no se llama en read_new_lines — es responsabilidad del caller
        reader._save_cursor.assert_not_called()

        # Llamar save_cursor manualmente (como haría el notificador)
        reader.save_cursor(new_cursor)
        reader._save_cursor.assert_called_once()
        args = reader._save_cursor.call_args[0][0]
        self.assertEqual(args["offset_bytes"], len(content))


# ---------------------------------------------------------------------------
# Tests de _parse_clip_rows del notificador
# ---------------------------------------------------------------------------

class TestParseClipRows(unittest.TestCase):

    def _make_notifier(self):
        from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
        settings = _make_settings()
        # Evitar que el constructor intente conectarse
        with patch.object(RemoteClipTelegramNotifier, "__init__", lambda self, s, **kw: None):
            notifier = RemoteClipTelegramNotifier.__new__(RemoteClipTelegramNotifier)
        notifier.settings = settings
        return notifier

    def test_video_event_rows_are_parsed(self):
        from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
        notifier = self._make_notifier()
        rows = [
            {"type": "clip", "cam_id": "cam1", "ts": 1000, "clip_file": "v.mp4"},
            {"type": "clips_movimiento", "cam_id": "cam1", "ts": 1001, "clip_file": "m.mp4"},
            {"type": "person", "cam_id": "cam1", "ts": 1001},
            {"type": "plate", "cam_id": "cam1", "ts": 1002},
        ]
        clips = notifier._parse_clip_rows(rows)
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0].cam_id, "cam1")
        self.assertEqual(clips[0].event_type, "clip")
        self.assertEqual(clips[1].event_type, "clips_movimiento")

    def test_clip_without_cam_id_is_skipped(self):
        notifier = self._make_notifier()
        rows = [{"type": "clip", "ts": 1000}]
        clips = notifier._parse_clip_rows(rows)
        self.assertEqual(clips, [])

    def test_uid_is_deterministic(self):
        notifier = self._make_notifier()
        row = {"type": "clip", "cam_id": "cam1", "ts": 1000, "clip_file": "vid.mp4"}
        clips1 = notifier._parse_clip_rows([row])
        clips2 = notifier._parse_clip_rows([row])
        self.assertEqual(clips1[0].uid, clips2[0].uid)

    def test_different_timestamps_produce_different_uids(self):
        notifier = self._make_notifier()
        rows = [
            {"type": "clip", "cam_id": "cam1", "ts": 1000, "clip_file": "v.mp4"},
            {"type": "clip", "cam_id": "cam1", "ts": 2000, "clip_file": "v.mp4"},
        ]
        clips = notifier._parse_clip_rows(rows)
        self.assertNotEqual(clips[0].uid, clips[1].uid)

    def test_relative_video_path_resolved_to_absolute(self):
        notifier = self._make_notifier()
        rows = [{"type": "clip", "cam_id": "cam1", "ts": 1, "clip_file": "video.mp4"}]
        clips = notifier._parse_clip_rows(rows)
        self.assertTrue(clips[0].video_path.startswith("/base/cam1/"))

    def test_absolute_video_path_kept_as_is(self):
        notifier = self._make_notifier()
        rows = [{"type": "clip", "cam_id": "cam1", "ts": 1, "clip_file": "/abs/path/video.mp4"}]
        clips = notifier._parse_clip_rows(rows)
        self.assertEqual(clips[0].video_path, "/abs/path/video.mp4")

    def test_telegram_message_labels_clip_and_motion(self):
        notifier = self._make_notifier()
        rows = [
            {"type": "clip", "cam_id": "cam1", "ts": 1, "clip_file": "zona.mp4"},
            {"type": "clips_movimiento", "cam_id": "cam1", "ts": 2, "clip_file": "mov.mp4"},
        ]
        clips = notifier._parse_clip_rows(rows)
        self.assertIn("Tipo de evento: zona", notifier._message_for_clip(clips[0]))
        self.assertIn("Tipo de evento: movimiento", notifier._message_for_clip(clips[1]))


# ---------------------------------------------------------------------------
# Tests de TelegramAlertWorker (sin DB real)
# ---------------------------------------------------------------------------

class TestTelegramAlertWorkerBackoff(unittest.TestCase):

    def _make_worker(self, send_fn=None):
        from back.app.services.telegram_alert_worker import TelegramAlertWorker, _BACKOFF_SECONDS

        noop = lambda *a, **kw: {"sent": 1}
        worker = TelegramAlertWorker(
            db_dsn="postgresql://x:x@localhost/x",
            send_video_fn=send_fn or noop,
            send_photo_fn=send_fn or noop,
            send_text_fn=send_fn or noop,
            cache_remote_file_fn=lambda p: Path(p),
            render_video_fn=lambda p: p,
        )
        worker.ensure_schema = MagicMock()
        return worker

    def test_successful_dispatch_calls_mark_sent(self):
        worker = self._make_worker(send_fn=lambda msg, path=None: {"sent": 2})
        worker._mark_sent = MagicMock()
        worker._mark_failed = MagicMock()
        row = {
            "id": "uuid-1", "event_uid": "uid-1",
            "camera_id": "cam1", "event_type": "clip",
            "attempts": 0,
            "telegram_payload": {"message": "hola", "remote_video": "", "remote_crop": ""},
        }
        result = worker._process_row(row)
        self.assertTrue(result)
        worker._mark_sent.assert_called_once_with("uuid-1")
        worker._mark_failed.assert_not_called()

    def test_failed_dispatch_increments_attempts(self):
        def fail(*a, **kw):
            raise RuntimeError("Timeout")

        worker = self._make_worker(send_fn=fail)
        worker._mark_sent = MagicMock()
        worker._mark_failed = MagicMock()
        row = {
            "id": "uuid-2", "event_uid": "uid-2",
            "camera_id": "cam1", "event_type": "clip",
            "attempts": 2,
            "telegram_payload": {"message": "x", "remote_video": "", "remote_crop": ""},
        }
        result = worker._process_row(row)
        self.assertFalse(result)
        worker._mark_failed.assert_called_once()
        call_args = worker._mark_failed.call_args[0]
        self.assertEqual(call_args[2], 3)  # attempts = 2 + 1

    def test_dead_letter_after_max_attempts(self):
        from back.app.services.telegram_alert_worker import _MAX_ATTEMPTS

        captured: list[str] = []

        def fake_mark_failed(outbox_id, error, attempts):
            from back.app.services.telegram_alert_worker import _MAX_ATTEMPTS
            is_dead = attempts >= _MAX_ATTEMPTS
            captured.append("dead_letter" if is_dead else "failed")

        def fail(*a, **kw):
            raise RuntimeError("siempre falla")

        worker = self._make_worker(send_fn=fail)
        worker._mark_sent = MagicMock()
        worker._mark_failed = fake_mark_failed

        row = {
            "id": "uuid-3", "event_uid": "uid-3",
            "camera_id": "cam1", "event_type": "clip",
            "attempts": _MAX_ATTEMPTS - 1,
            "telegram_payload": {"message": "x", "remote_video": "", "remote_crop": ""},
        }
        worker._process_row(row)
        self.assertEqual(captured, ["dead_letter"])

    def test_dispatch_chooses_video_over_photo(self):
        calls: list[str] = []

        def send_video(msg, path):
            calls.append("video")
            return {"sent": 1}

        def send_photo(msg, path):
            calls.append("photo")
            return {"sent": 1}

        worker = self._make_worker()
        worker._send_video = send_video
        worker._send_photo = send_photo
        worker._cache_remote_file = lambda p: Path("/tmp/fake.mp4")
        worker._render_video = lambda p: p

        payload = {"message": "test", "remote_video": "/remote/v.mp4", "remote_crop": "/remote/c.jpg"}
        worker._dispatch(payload)
        self.assertEqual(calls, ["video"])

    def test_dispatch_uses_photo_when_no_video(self):
        calls: list[str] = []

        def send_video(msg, path):
            calls.append("video")
            return {"sent": 1}

        def send_photo(msg, path):
            calls.append("photo")
            return {"sent": 1}

        worker = self._make_worker()
        worker._send_video = send_video
        worker._send_photo = send_photo
        worker._cache_remote_file = lambda p: Path("/tmp/fake.jpg")
        worker._render_video = lambda p: p

        payload = {"message": "test", "remote_video": "", "remote_crop": "/remote/c.jpg"}
        worker._dispatch(payload)
        self.assertEqual(calls, ["photo"])

    def test_dispatch_uses_text_when_no_media(self):
        calls: list[str] = []

        def send_text(msg):
            calls.append("text")
            return {"sent": 1}

        worker = self._make_worker()
        worker._send_text = send_text

        payload = {"message": "solo texto", "remote_video": "", "remote_crop": ""}
        worker._dispatch(payload)
        self.assertEqual(calls, ["text"])


# ---------------------------------------------------------------------------
# Tests de deduplicación de event_uid (semánticos, sin DB)
# ---------------------------------------------------------------------------

class TestEventUidDeduplication(unittest.TestCase):

    def test_same_clip_row_produces_same_uid(self):
        from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
        settings = _make_settings()
        with patch.object(RemoteClipTelegramNotifier, "__init__", lambda self, s, **kw: None):
            notifier = RemoteClipTelegramNotifier.__new__(RemoteClipTelegramNotifier)
        notifier.settings = settings

        row = {"type": "clip", "cam_id": "cam1", "ts": 1700000000, "clip_file": "video.mp4"}
        clips1 = notifier._parse_clip_rows([row])
        clips2 = notifier._parse_clip_rows([row])
        self.assertEqual(clips1[0].uid, clips2[0].uid)

    def test_burst_of_clips_have_different_uids(self):
        from back.app.services.remote_clip_telegram_notifier import RemoteClipTelegramNotifier
        settings = _make_settings()
        with patch.object(RemoteClipTelegramNotifier, "__init__", lambda self, s, **kw: None):
            notifier = RemoteClipTelegramNotifier.__new__(RemoteClipTelegramNotifier)
        notifier.settings = settings

        rows = [
            {"type": "clip", "cam_id": "cam1", "ts": 1000 + i, "clip_file": f"v{i}.mp4"}
            for i in range(10)
        ]
        clips = notifier._parse_clip_rows(rows)
        uids = {c.uid for c in clips}
        self.assertEqual(len(uids), 10)


if __name__ == "__main__":
    unittest.main()
