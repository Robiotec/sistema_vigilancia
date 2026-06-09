from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable

import paramiko


@dataclass(frozen=True, slots=True)
class SSHConnectionConfig:
    host: str
    user: str
    password: str | None = None
    port: int = 22
    key_path: str | None = None
    timeout: float = 10.0


@dataclass(frozen=True, slots=True)
class RemoteFileSnapshot:
    path: str
    exists: bool
    size: int = 0
    modified_at: float = 0.0
    sha256: str = ""
    content: str = ""


@dataclass(frozen=True, slots=True)
class RemoteFileChangeEvent:
    event_type: str
    path: str
    previous: RemoteFileSnapshot | None
    current: RemoteFileSnapshot
    appended_lines: tuple[str, ...] = ()

    def jsonl_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for line in self.appended_lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return items


class RemoteFileWatcher:
    """Observa un archivo remoto por SSH sin bloquear el flujo principal.

    - Corre en un hilo daemon.
    - Detecta creacion, modificacion, truncado y borrado.
    - Puede entregar lineas nuevas para archivos JSONL.
    """

    def __init__(
        self,
        connection: SSHConnectionConfig,
        remote_path: str,
        *,
        poll_interval: float = 0.5,
        read_full_content: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        self.connection = connection
        self.remote_path = str(PurePosixPath(remote_path))
        self.poll_interval = max(0.2, float(poll_interval))
        self.read_full_content = read_full_content
        self.encoding = encoding
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._on_change: Callable[[RemoteFileChangeEvent], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None
        self._last_snapshot: RemoteFileSnapshot | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        on_change: Callable[[RemoteFileChangeEvent], None],
        *,
        on_error: Callable[[Exception], None] | None = None,
        emit_initial: bool = False,
    ) -> None:
        if self.is_running:
            raise RuntimeError("El watcher ya está en ejecución")

        self._on_change = on_change
        self._on_error = on_error
        self._stop_event.clear()
        self._connect()
        self._last_snapshot = self._read_snapshot()

        if emit_initial and self._last_snapshot.exists:
            self._emit_event(
                RemoteFileChangeEvent(
                    event_type="initial",
                    path=self.remote_path,
                    previous=None,
                    current=self._last_snapshot,
                    appended_lines=tuple(self._extract_lines("", self._last_snapshot.content)),
                )
            )

        self._thread = threading.Thread(target=self._watch_loop, name="remote-file-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._disconnect()

    def read_now(self) -> RemoteFileSnapshot:
        if self._sftp is None:
            self._connect()
        return self._read_snapshot()

    def _connect(self) -> None:
        self._disconnect()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": self.connection.host,
            "username": self.connection.user,
            "port": self.connection.port,
            "timeout": self.connection.timeout,
        }
        if self.connection.key_path:
            key = paramiko.RSAKey.from_private_key_file(self.connection.key_path)
            connect_kwargs["pkey"] = key
        else:
            connect_kwargs["password"] = self.connection.password

        client.connect(**connect_kwargs)
        self._client = client
        self._sftp = client.open_sftp()

    def _disconnect(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def _watch_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                current = self._read_snapshot()
                previous = self._last_snapshot

                if self._has_changed(previous, current):
                    event_type = self._classify_event(previous, current)
                    appended_lines = tuple(self._resolve_appended_lines(previous, current))
                    self._emit_event(
                        RemoteFileChangeEvent(
                            event_type=event_type,
                            path=self.remote_path,
                            previous=previous,
                            current=current,
                            appended_lines=appended_lines,
                        )
                    )
                    self._last_snapshot = current
            except Exception as exc:
                self._emit_error(exc)
                try:
                    self._connect()
                except Exception as reconnect_exc:
                    self._emit_error(reconnect_exc)
            finally:
                self._stop_event.wait(self.poll_interval)

    def _read_snapshot(self) -> RemoteFileSnapshot:
        if self._sftp is None:
            raise RuntimeError("No hay conexión SFTP activa")

        try:
            stat_result = self._sftp.stat(self.remote_path)
        except FileNotFoundError:
            return RemoteFileSnapshot(path=self.remote_path, exists=False)

        size = int(getattr(stat_result, "st_size", 0) or 0)
        modified_at = float(getattr(stat_result, "st_mtime", 0.0) or 0.0)
        content = ""
        sha256 = ""

        if self.read_full_content and size >= 0:
            with self._sftp.open(self.remote_path, "rb") as remote_file:
                raw = remote_file.read()
            sha256 = hashlib.sha256(raw).hexdigest()
            content = raw.decode(self.encoding, errors="replace")

        return RemoteFileSnapshot(
            path=self.remote_path,
            exists=True,
            size=size,
            modified_at=modified_at,
            sha256=sha256,
            content=content,
        )

    @staticmethod
    def _has_changed(previous: RemoteFileSnapshot | None, current: RemoteFileSnapshot) -> bool:
        if previous is None:
            return False
        if previous.exists != current.exists:
            return True
        if not current.exists:
            return False
        return (
            previous.size != current.size
            or previous.modified_at != current.modified_at
            or previous.sha256 != current.sha256
        )

    @staticmethod
    def _classify_event(previous: RemoteFileSnapshot | None, current: RemoteFileSnapshot) -> str:
        if previous is None and current.exists:
            return "created"
        if previous and previous.exists and not current.exists:
            return "deleted"
        if previous and not previous.exists and current.exists:
            return "created"
        if previous and current.size < previous.size:
            return "truncated"
        return "modified"

    @staticmethod
    def _extract_lines(previous_content: str, current_content: str) -> list[str]:
        if not current_content:
            return []
        if not previous_content:
            return current_content.splitlines()
        if current_content.startswith(previous_content):
            delta = current_content[len(previous_content):]
            return delta.splitlines()
        return current_content.splitlines()

    def _resolve_appended_lines(
        self,
        previous: RemoteFileSnapshot | None,
        current: RemoteFileSnapshot,
    ) -> list[str]:
        if not current.exists or not self.read_full_content:
            return []
        previous_content = previous.content if previous else ""
        return self._extract_lines(previous_content, current.content)

    def _emit_event(self, event: RemoteFileChangeEvent) -> None:
        if self._on_change is not None:
            self._on_change(event)

    def _emit_error(self, error: Exception) -> None:
        if self._on_error is not None:
            self._on_error(error)
