from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import mimetypes
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import paramiko

from back.app.config import Settings
from back.app.services.send_telegram import (
    send_configured_telegram_photo,
    send_configured_telegram_text,
    send_configured_telegram_video,
)

ECUADOR_TZ = timezone(timedelta(hours=-5))


@dataclass(frozen=True, slots=True)
class ClipAlert:
    uid: str
    cam_id: str
    timestamp: int
    crop_path: str
    video_path: str
    json_path: str
    track_id: str
    payload: dict[str, Any]
    manifest_payload: dict[str, Any]


class RemoteClipTelegramNotifier:
    """Vigila el manifest remoto y envia por Telegram nuevos eventos type=clip con crop."""

    def __init__(self, settings: Settings, *, poll_interval: float = 3.0) -> None:
        self.settings = settings
        self.poll_interval = max(1.0, float(poll_interval))
        self.data_dir = Path(__file__).resolve().parents[1] / "data"
        self.crop_cache_dir = self.data_dir / "telegram_clip_crops"
        self.state_path = self.data_dir / "clip_telegram_notifier_state.json"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "running": False,
            "last_error": "",
            "last_checked_at": "",
            "last_notified_uid": "",
            "last_notified_at": "",
            "last_sent_total": 0,
            "last_delivery_detail": "",
            "last_video_path": "",
            "last_rendered_video_path": "",
        }

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="remote-clip-telegram-notifier", daemon=True)
        self._thread.start()
        self._set_status(running=True)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._set_status(running=False)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def check_once(self, *, seed_existing: bool = False) -> dict[str, Any]:
        state = self._load_state()
        clips = self._read_latest_clips(limit=10)
        now = self._iso_now()
        self._set_status(last_checked_at=now, last_error="")

        if seed_existing and not state.get("seen_uids"):
            for clip in clips:
                state["seen_uids"].append(clip.uid)
            self._save_state(state)
            return {"checked": len(clips), "sent": 0, "seeded": len(clips)}

        sent = 0
        skipped = 0
        seen_uids = set(state.get("seen_uids", []))
        unseen_clips = [clip for clip in clips if clip.uid not in seen_uids]
        latest_clip = max(unseen_clips, key=lambda item: item.timestamp, default=None)

        for clip in unseen_clips:
            if clip is not latest_clip:
                state["seen_uids"].append(clip.uid)
                skipped += 1

        if latest_clip is not None:
            if latest_clip.video_path:
                local_video = self._cache_remote_file(latest_clip.video_path)
                rendered_video = self._render_telegram_video(local_video)
                delivery = send_configured_telegram_video(
                    message=self._message_for_clip(latest_clip),
                    video_path=rendered_video,
                )
                self._set_status(
                    last_video_path=str(local_video),
                    last_rendered_video_path=str(rendered_video),
                )
            elif latest_clip.crop_path:
                local_crop = self._cache_remote_file(latest_clip.crop_path)
                delivery = send_configured_telegram_photo(
                    message=self._message_for_clip(latest_clip),
                    image_path=local_crop,
                )
            else:
                delivery = send_configured_telegram_text(message=self._message_for_clip(latest_clip))

            if delivery is not None:
                sent = int(delivery.get("sent") or 0)
                detail = self._delivery_detail(delivery)
                self._set_status(last_delivery_detail=detail)
                if sent <= 0:
                    raise RuntimeError(detail or "Telegram no confirmo el envio")
                state["seen_uids"].append(latest_clip.uid)
                state["notified_uids"].append(latest_clip.uid)
                state["last_notified_uid"] = latest_clip.uid
                state["last_notified_at"] = self._iso_now()
                self._set_status(
                    last_notified_uid=latest_clip.uid,
                    last_notified_at=state["last_notified_at"],
                    last_sent_total=sent,
                )

        state["seen_uids"] = state.get("seen_uids", [])[-1000:]
        state["notified_uids"] = state.get("notified_uids", [])[-1000:]
        self._save_state(state)
        return {"checked": len(clips), "sent": sent, "skipped": skipped}

    def _run_loop(self) -> None:
        seeded = False
        while not self._stop_event.is_set():
            try:
                self.check_once(seed_existing=not seeded)
                seeded = True
            except Exception as exc:
                self._set_status(last_error=str(exc), last_checked_at=self._iso_now())
            finally:
                self._stop_event.wait(self.poll_interval)
        self._set_status(running=False)

    def _read_latest_clips(self, *, limit: int) -> list[ClipAlert]:
        remote_python = f"""
import json
from pathlib import Path

base = Path({self.settings.ssh_events_base_path!r})
manifest = base / "manifest.jsonl"
limit = {max(1, min(int(limit), 50))}
items = []

def resolve_path(value, cam_id=""):
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates = [
            base / cam_id / raw,
            base / raw,
            path,
        ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])

def first_text(source, keys):
    if not isinstance(source, dict):
        return ""
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""

if manifest.exists():
    with manifest.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("type") or "").strip() != "clip":
                continue
            cam_id = str(row.get("cam_id") or "").strip()
            payload = dict(row)
            json_path = resolve_path(row.get("json_file"), cam_id)
            if json_path and Path(json_path).exists():
                try:
                    loaded = json.loads(Path(json_path).read_text(encoding="utf-8", errors="replace"))
                    if isinstance(loaded, dict):
                        payload.update(loaded)
                except Exception:
                    pass
            crop_path = (
                first_text(payload, ("crop_path", "crop_file", "crop", "image_path", "image_file", "source_image", "frame_path", "thumbnail_path"))
                or first_text(row, ("crop_path", "crop_file", "crop", "image_path", "image_file", "source_image", "frame_path", "thumbnail_path"))
            )
            video_path = first_text(row, ("clip_file", "file")) or first_text(payload, ("clip_file", "video_path", "clip_path"))
            timestamp = int(float(payload.get("timestamp") or row.get("ts") or row.get("timestamp") or 0))
            resolved_crop = resolve_path(crop_path, cam_id) if crop_path else ""
            if resolved_crop and not Path(resolved_crop).exists():
                resolved_crop = ""
            resolved_video = resolve_path(video_path, cam_id) if video_path else ""
            uid_source = "|".join([
                cam_id,
                "clip",
                str(timestamp),
                str(payload.get("track_id") or row.get("track_id") or ""),
                resolved_crop,
                resolved_video,
                json_path,
            ])
            items.append({{
                "uid_source": uid_source,
                "cam_id": cam_id,
                "timestamp": timestamp,
                "crop_path": resolved_crop,
                "video_path": resolved_video,
                "json_path": json_path,
                "track_id": str(payload.get("track_id") or row.get("track_id") or "").strip(),
                "payload": payload,
                "manifest_payload": row,
            }})

print(json.dumps({{"items": items[-limit:]}}, ensure_ascii=False))
"""
        output = self._run_remote_python(remote_python)
        parsed = json.loads(output) if output else {}
        items = parsed.get("items") if isinstance(parsed, dict) else []
        clips: list[ClipAlert] = []
        for item in items if isinstance(items, list) else []:
            uid_source = str(item.get("uid_source") or "")
            uid = hashlib.sha256(uid_source.encode("utf-8")).hexdigest()
            clips.append(
                ClipAlert(
                    uid=uid,
                    cam_id=str(item.get("cam_id") or "").strip(),
                    timestamp=self._int_value(item.get("timestamp")),
                    crop_path=str(item.get("crop_path") or "").strip(),
                    video_path=str(item.get("video_path") or "").strip(),
                    json_path=str(item.get("json_path") or "").strip(),
                    track_id=str(item.get("track_id") or "").strip(),
                    payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
                    manifest_payload=item.get("manifest_payload") if isinstance(item.get("manifest_payload"), dict) else {},
                )
            )
        return clips

    def _run_remote_python(self, script: str) -> str:
        command = "python3 - <<'PY'\n" + script.strip() + "\nPY"
        with self._client() as client:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise RuntimeError(error or f"Comando remoto fallo con codigo {exit_status}")
        return output

    def _cache_remote_file(self, remote_path: str) -> Path:
        normalized_path = str(PurePosixPath(remote_path or "")).strip()
        if not normalized_path:
            raise FileNotFoundError("Ruta remota vacia")

        suffix = PurePosixPath(normalized_path).suffix or mimetypes.guess_extension(
            mimetypes.guess_type(normalized_path)[0] or ""
        ) or ".jpg"
        cache_key = hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
        local_path = self.crop_cache_dir / f"{cache_key}{suffix}"
        partial_path = local_path.with_suffix(f"{local_path.suffix}.part")

        self.crop_cache_dir.mkdir(parents=True, exist_ok=True)
        if local_path.exists() and local_path.stat().st_size > 0:
            return local_path

        with self._client() as client:
            with client.open_sftp() as sftp:
                self._wait_remote_file_stable(sftp, normalized_path)
                with sftp.open(normalized_path, "rb") as remote_file:
                    with partial_path.open("wb") as local_file:
                        while True:
                            chunk = remote_file.read(1024 * 1024)
                            if not chunk:
                                break
                            local_file.write(chunk)
                partial_path.replace(local_path)
        return local_path

    @staticmethod
    def _wait_remote_file_stable(sftp: paramiko.SFTPClient, normalized_path: str) -> None:
        previous_size = -1
        stable_reads = 0
        for _ in range(8):
            stat_result = sftp.stat(normalized_path)
            size = int(getattr(stat_result, "st_size", 0) or 0)
            if size > 0 and size == previous_size:
                stable_reads += 1
                if stable_reads >= 2:
                    return
            else:
                stable_reads = 0
            previous_size = size
            time.sleep(0.75)

    def _render_telegram_video(self, source_path: Path) -> Path:
        rendered_path = source_path.with_suffix(".telegram.mp4")
        if rendered_path.exists() and rendered_path.stat().st_size > 0:
            return rendered_path

        partial_path = rendered_path.with_suffix(f"{rendered_path.suffix}.part")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(partial_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "No se pudo renderizar el video para Telegram")
        partial_path.replace(rendered_path)
        if rendered_path.stat().st_size > 45 * 1024 * 1024:
            return self._render_small_telegram_video(source_path, rendered_path)
        return rendered_path

    @staticmethod
    def _render_small_telegram_video(source_path: Path, rendered_path: Path) -> Path:
        small_path = source_path.with_suffix(".telegram-small.mp4")
        if small_path.exists() and small_path.stat().st_size > 0:
            return small_path

        partial_path = small_path.with_suffix(f"{small_path.suffix}.part")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            "scale='min(854,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "32",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(partial_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "No se pudo reducir el video para Telegram")
        partial_path.replace(small_path)
        try:
            rendered_path.unlink()
        except OSError:
            pass
        return small_path

    @staticmethod
    def _delivery_detail(delivery: dict[str, Any]) -> str:
        results = delivery.get("results") if isinstance(delivery.get("results"), list) else []
        if not results:
            return ""
        return "; ".join(
            f"{item.get('chat_id')}: {item.get('detail')}"
            for item in results
            if isinstance(item, dict)
        )

    def _client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.settings.ssh_events_host,
            username=self.settings.ssh_events_user,
            password=self.settings.ssh_events_password,
            port=self.settings.ssh_events_port,
            timeout=10,
        )
        return _SSHClientContext(client)

    def _message_for_clip(self, clip: ClipAlert) -> str:
        detected_at = "Sin dato"
        if clip.timestamp:
            detected_at = datetime.fromtimestamp(clip.timestamp, tz=ECUADOR_TZ).strftime("%d/%m/%Y %H:%M:%S")
        rows = [
            "ALERTA",
            "",
            "Nuevo clip detectado.",
            "",
            f"Camara: {clip.cam_id or 'Sin dato'}",
            f"Hora: {detected_at}",
        ]
        if clip.track_id:
            rows.append(f"Track ID: {clip.track_id}")
        if clip.video_path:
            rows.append(f"Video: {PurePosixPath(clip.video_path).name}")
        return "\n".join(rows)

    def _load_state(self) -> dict[str, Any]:
        default = {"seen_uids": [], "notified_uids": [], "last_notified_uid": "", "last_notified_at": ""}
        if not self.state_path.is_file():
            return default
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        if not isinstance(payload, dict):
            return default
        return {
            "seen_uids": self._normalized_list(payload.get("seen_uids")),
            "notified_uids": self._normalized_list(payload.get("notified_uids")),
            "last_notified_uid": str(payload.get("last_notified_uid") or ""),
            "last_notified_at": str(payload.get("last_notified_at") or ""),
        }

    def _save_state(self, state: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)

    @staticmethod
    def _normalized_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()


class _SSHClientContext:
    def __init__(self, client: paramiko.SSHClient) -> None:
        self.client = client

    def __enter__(self) -> paramiko.SSHClient:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()
