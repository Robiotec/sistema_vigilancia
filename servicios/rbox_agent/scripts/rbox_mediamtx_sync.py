#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_ENV_FILE = "/robiotec/mediamtx/.env"
DEFAULT_ORCHESTRATOR_BASE = "https://robio-ai.com/api/orchestrator"
DEFAULT_MEDIAMTX_API = "http://127.0.0.1:9997"


running = True


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


load_env_file(env_first("RBOX_ENV_FILE", default=DEFAULT_ENV_FILE))

ORCHESTRATOR_BASE = env_first(
    "RBOX_ORCHESTRATOR_BASE",
    "API_ORCHESTRATOR_BASE",
    default=DEFAULT_ORCHESTRATOR_BASE,
).rstrip("/")
MEDIAMTX_API = env_first("RBOX_MEDIAMTX_API", "MEDIAMTX_API", default=DEFAULT_MEDIAMTX_API).rstrip("/")
RBOX_KEY = env_first("RBOX_KEY", "RBOX_SERIAL")
SERVICE_TOKEN = env_first(
    "RBOX_SERVICE_TOKEN",
    "API_ORCHESTRATOR_TOKEN",
    "API_INGEST_TOKEN",
    "SERVICE_INGEST_TOKEN",
)
CHECK_INTERVAL = float(env_first("RBOX_CHECK_INTERVAL", default="5"))
ACTIVE_ONLY = env_bool("RBOX_ACTIVE_ONLY", True)
VERIFY_TLS = env_bool("RBOX_API_VERIFY_TLS", True)
PUBLISH_TRANSPORT = env_first("RBOX_PUBLISH_TRANSPORT", default="srt").lower()
LOCAL_RTSP_PORT = int(env_first("RBOX_LOCAL_RTSP_PORT", "RTSP_PORT", default="8554"))
FFMPEG_BIN = env_first("RBOX_FFMPEG_BIN", default="/usr/bin/ffmpeg")
FFMPEG_LOG_LEVEL = env_first("RBOX_FFMPEG_LOG_LEVEL", default="warning")
CAMERA_PROBE_TIMEOUT = float(env_first("RBOX_CAMERA_PROBE_TIMEOUT", default="2.0"))
STATE_FILE = Path(env_first("RBOX_SYNC_STATE_FILE", default="/robiotec/mediamtx/.rbox_sync_state.json"))
last_camera_reachability: dict[str, bool] = {}


def api_context():
    if VERIFY_TLS:
        return None
    import ssl

    return ssl._create_unverified_context()


def request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if SERVICE_TOKEN:
        headers["X-Robiotec-Ingest-Token"] = SERVICE_TOKEN
    req = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=10, context=api_context()) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No se pudo conectar a {url}: {exc}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def mediamtx_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{MEDIAMTX_API}{path}"
    return request_json(url, method=method, payload=payload)


def encoded_path(path: str) -> str:
    return quote(path.strip("/"), safe="")


def fetch_rbox_cameras() -> tuple[list[dict[str, Any]], float]:
    if not RBOX_KEY:
        raise RuntimeError("Falta RBOX_KEY o RBOX_SERIAL en el entorno")
    if not SERVICE_TOKEN:
        raise RuntimeError("Falta RBOX_SERVICE_TOKEN/API_ORCHESTRATOR_TOKEN/SERVICE_INGEST_TOKEN")
    query = urlencode(
        {
            "active_only": "true" if ACTIVE_ONLY else "false",
            "poll_after_seconds": str(int(CHECK_INTERVAL)),
        }
    )
    url = f"{ORCHESTRATOR_BASE}/rboxes/{encoded_path(RBOX_KEY)}/cameras?{query}"
    payload = request_json(url)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    poll_after = payload.get("poll_after_seconds", CHECK_INTERVAL) if isinstance(payload, dict) else CHECK_INTERVAL
    return list(items), max(1.0, float(poll_after or CHECK_INTERVAL))


def legacy_env_paths() -> set[str]:
    paths: set[str] = set()
    index = 1
    while True:
        ip = os.getenv(f"CAM{index}_IP", "").strip()
        channel = os.getenv(f"CAM{index}_CH1", "").strip()
        if not ip:
            break
        if channel:
            paths.add(channel.strip("/"))
        index += 1
    return paths


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"managed_paths": []}
    except Exception as exc:
        log(f"Estado local invalido, se recreara: {exc}")
        return {"managed_paths": []}


def save_state(paths: set[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"managed_paths": sorted(paths), "updated_at": time.time()}
    STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def list_path_configs() -> dict[str, dict[str, Any]]:
    payload = mediamtx_json("/v3/config/paths/list")
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {str(item.get("name", "")).strip("/"): item for item in items if item.get("name")}


def camera_source_reachable(camera: dict[str, Any]) -> bool:
    path = str(camera.get("mediamtx_path") or camera.get("unique_code") or "").strip("/")
    source = str(camera.get("rtsp_url") or "").strip()
    parsed = urlparse(source)
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        return True
    host = parsed.hostname
    port = parsed.port or 554
    if not host:
        return False

    try:
        with socket.create_connection((host, port), timeout=CAMERA_PROBE_TIMEOUT):
            reachable = True
    except OSError:
        reachable = False

    previous = last_camera_reachability.get(path)
    if previous is not reachable:
        state = "disponible" if reachable else "sin conexion local"
        log(f"Camara {path or source} {state} ({host}:{port})")
        last_camera_reachability[path] = reachable
    return reachable


def central_publish_target(camera: dict[str, Any]) -> str:
    path = str(camera.get("mediamtx_path") or camera.get("unique_code") or "").strip("/")
    output_url = str(camera.get("output_url") or camera.get("output_rtsp_url") or "").strip()
    if PUBLISH_TRANSPORT == "rtsp":
        if not output_url.startswith("rtsp://"):
            raise RuntimeError(f"La camara {path} no tiene output RTSP")
        return output_url

    parsed = urlparse(output_url) if output_url else None
    host = env_first("RBOX_SRT_HOST", "SRT_HOST", default=(parsed.hostname if parsed else "") or "207.246.68.223")
    port = env_first("RBOX_SRT_PORT", "SRT_PORT", default="8890")
    return f"srt://{host}:{port}?streamid=publish:{path}&pkt_size=1316"


def run_on_ready_command(camera: dict[str, Any]) -> str:
    path = str(camera.get("mediamtx_path") or camera.get("unique_code") or "").strip("/")
    local_url = f"rtsp://127.0.0.1:{LOCAL_RTSP_PORT}/{path}"
    target = central_publish_target(camera)
    command = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        FFMPEG_LOG_LEVEL,
        "-nostdin",
        "-rtsp_transport",
        "tcp",
        "-i",
        local_url,
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
    ]
    if target.startswith("srt://"):
        command.extend(["-f", "mpegts", target])
    elif target.startswith("rtsp://"):
        command.extend(["-f", "rtsp", "-rtsp_transport", "tcp", target])
    else:
        raise RuntimeError(f"Destino no soportado para {path}: {target}")
    return " ".join(shlex.quote(part) for part in command)


def target_path_config(camera: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    path = str(camera.get("mediamtx_path") or camera.get("unique_code") or "").strip("/")
    source = str(camera.get("rtsp_url") or "").strip()
    if not path or not source:
        raise RuntimeError(f"Camara incompleta recibida desde API central: {camera!r}")
    return path, {
        "source": source,
        "rtspTransport": "tcp",
        "runOnReady": run_on_ready_command(camera),
        "runOnReadyRestart": True,
        "overridePublisher": True,
    }


def config_signature(config: dict[str, Any]) -> str:
    relevant = {
        "source": config.get("source") or "",
        "rtspTransport": config.get("rtspTransport") or "",
        "runOnReady": config.get("runOnReady") or "",
        "runOnReadyRestart": bool(config.get("runOnReadyRestart")),
        "overridePublisher": bool(config.get("overridePublisher")),
    }
    encoded = json.dumps(relevant, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def add_or_patch_path(path: str, config: dict[str, Any], current: dict[str, dict[str, Any]]) -> None:
    action = "patch" if path in current else "add"
    endpoint = f"/v3/config/paths/{action}/{encoded_path(path)}"
    mediamtx_json(endpoint, method="PATCH" if action == "patch" else "POST", payload=config)
    log(f"MediaMTX {action}: {path}")


def delete_path(path: str, current: dict[str, dict[str, Any]]) -> None:
    if path not in current:
        return
    try:
        mediamtx_json(f"/v3/config/paths/delete/{encoded_path(path)}", method="DELETE")
        log(f"MediaMTX delete: {path}")
    except Exception as exc:
        log(f"No se pudo eliminar {path}: {exc}")


def sync_once() -> float:
    cameras, poll_after = fetch_rbox_cameras()
    current = list_path_configs()
    state = load_state()
    managed_paths = set(state.get("managed_paths") or []) | legacy_env_paths()

    targets: dict[str, dict[str, Any]] = {}
    for camera in cameras:
        if not camera_source_reachable(camera):
            continue
        path, config = target_path_config(camera)
        targets[path] = config

    for path, config in sorted(targets.items()):
        current_config = current.get(path)
        if current_config and config_signature(current_config) == config_signature(config):
            continue
        add_or_patch_path(path, config, current)
        current[path] = config

    for path in sorted(managed_paths - set(targets)):
        delete_path(path, current)
        current.pop(path, None)

    save_state(set(targets))
    log(f"Sincronizadas {len(targets)} camaras para RBox {RBOX_KEY}")
    return poll_after


def shutdown_handler(signum, _frame) -> None:
    global running
    log(f"Senal {signum} recibida; apagando sincronizador")
    running = False


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    log(
        "RBox MediaMTX sync iniciado "
        f"(api={ORCHESTRATOR_BASE}, mediamtx={MEDIAMTX_API}, transport={PUBLISH_TRANSPORT})"
    )
    sleep_for = CHECK_INTERVAL
    while running:
        try:
            sleep_for = sync_once()
        except Exception as exc:
            log(f"Error de sincronizacion: {exc}")
            sleep_for = CHECK_INTERVAL
        time.sleep(max(1.0, sleep_for))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
