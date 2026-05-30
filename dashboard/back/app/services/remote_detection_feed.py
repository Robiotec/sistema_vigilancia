from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import paramiko

from back.app.config import Settings


@dataclass(slots=True)
class RemoteCameraEvent:
    event_type: str
    cam_id: str
    timestamp: int
    source_file: str
    crop_path: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.payload)
        if self.event_type == "person":
            raw_name = str(payload.get("person_name") or "").strip()
            parts = raw_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            extra_info = payload.get("person_info") if isinstance(payload.get("person_info"), dict) else {}
            return {
                "event_type": self.event_type,
                "cam_id": self.cam_id,
                "timestamp": self.timestamp,
                "source_file": self.source_file,
                "crop_path": self.crop_path,
                "person_id": str(payload.get("person_id") or "").strip(),
                "person_name": raw_name,
                "display_title": "Persona detectada",
                "rows": [
                    {"label": "nombre", "value": extra_info.get("nombre") or first_name or raw_name or "Sin dato"},
                    {"label": "apellido", "value": extra_info.get("apellido") or last_name or "Sin dato"},
                    {"label": "Cedula", "value": str(payload.get("person_id") or extra_info.get("cedula") or "Sin dato")},
                ],
            }

        vehicle_info = payload.get("vehicle_info") if isinstance(payload.get("vehicle_info"), dict) else {}
        return {
            "event_type": self.event_type,
            "cam_id": self.cam_id,
            "timestamp": self.timestamp,
            "source_file": self.source_file,
            "crop_path": self.crop_path,
            "plate": str(payload.get("plate") or "").strip(),
            "display_title": "Vehículo detectado",
            "rows": [
                {"label": "placa", "value": str(payload.get("plate") or vehicle_info.get("Placa") or "Sin dato")},
                {"label": "marca", "value": str(vehicle_info.get("Marca") or "Sin dato")},
                {"label": "modelo", "value": str(vehicle_info.get("Modelo") or "Sin dato")},
            ],
        }


class RemoteDetectionFeedService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_camera_events(self, cam_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
        normalized_cam_id = str(cam_id or "").strip()
        if not normalized_cam_id:
            return []

        remote_python = f"""
import json
from pathlib import Path

base = Path({self.settings.ssh_events_base_path!r})
manifest = base / "manifest.jsonl"
cam_id = {normalized_cam_id!r}
limit = {max(1, min(int(limit), 24))}
items = []

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
            if str(row.get("cam_id") or "").strip() != cam_id:
                continue
            source_file = Path(str(row.get("file") or "").strip())
            if not source_file.exists():
                continue
            try:
                payload = json.loads(source_file.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            items.append({{
                "event_type": str(row.get("type") or "").strip(),
                "cam_id": cam_id,
                "timestamp": int(row.get("ts") or payload.get("timestamp") or 0),
                "source_file": str(source_file),
                "crop_path": str(payload.get("crop_path") or ""),
                "payload": payload,
            }})

print(json.dumps(items[-limit:], ensure_ascii=False))
"""
        output = self._run_python(remote_python)
        if not output:
            return []

        try:
            items = json.loads(output)
        except json.JSONDecodeError:
            return []

        events = [
            RemoteCameraEvent(
                event_type=str(item.get("event_type") or "").strip(),
                cam_id=str(item.get("cam_id") or "").strip(),
                timestamp=int(item.get("timestamp") or 0),
                source_file=str(item.get("source_file") or "").strip(),
                crop_path=str(item.get("crop_path") or "").strip(),
                payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
            )
            for item in items
        ]
        events.sort(key=lambda event: event.timestamp, reverse=True)
        return [event.to_dict() for event in events]

    def read_remote_file(self, remote_path: str) -> tuple[bytes, str]:
        normalized_path = str(PurePosixPath(remote_path or "")).strip()
        if not normalized_path:
            raise FileNotFoundError("Ruta remota vacía")

        with self._client() as client:
            with client.open_sftp() as sftp:
                with sftp.open(normalized_path, "rb") as remote_file:
                    content = remote_file.read()
        media_type, _ = mimetypes.guess_type(normalized_path)
        return content, media_type or "application/octet-stream"

    def _run_python(self, script: str) -> str:
        command = "python3 - <<'PY'\n" + script.strip() + "\nPY"
        with self._client() as client:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise RuntimeError(error or f"Comando remoto falló con código {exit_status}")
        return output

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


class _SSHClientContext:
    def __init__(self, client: paramiko.SSHClient) -> None:
        self.client = client

    def __enter__(self) -> paramiko.SSHClient:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()
