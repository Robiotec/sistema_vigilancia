from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from db.connection import db, DatabaseError

CHECK_INTERVAL = 5
MEDIAMTX_SERVER = "rtsp://207.246.68.223:8554"
LOG_DIR = Path("/tmp")

CAMERA_PROCESSES: dict[str, subprocess.Popen] = {}


def get_rbox_cameras() -> list[dict[str, Any]]:
    query = """
        SELECT
            c.id,
            c.name,
            c.unique_code,
            c.rtsp_url,
            c.channel,
            c.active,
            c.uses_rbox,
            c.rbox_id,
            r.name AS rbox_name,
            r.serial AS rbox_serial
        FROM cameras c
        INNER JOIN rboxes r
            ON c.rbox_id = r.id
        WHERE
            c.active = true
            AND c.uses_rbox = true
            AND c.rbox_id IS NOT NULL
            AND c.rtsp_url IS NOT NULL
            AND c.unique_code IS NOT NULL
            AND r.active = true;
    """

    return db.fetch_all(query)


def build_output_url(camera: dict[str, Any]) -> str:
    return f"{MEDIAMTX_SERVER}/{camera['unique_code']}"


def start_camera_push(camera: dict[str, Any]) -> None:
    camera_id = str(camera["id"])

    if camera_id in CAMERA_PROCESSES:
        process = CAMERA_PROCESSES[camera_id]

        if process.poll() is None:
            return

        print(
            f"FFmpeg muerto para cámara {camera_id}. "
            f"Código salida: {process.returncode}",
            flush=True,
        )
        CAMERA_PROCESSES.pop(camera_id, None)

    input_url = camera["rtsp_url"]
    output_url = build_output_url(camera)

    print("=" * 80, flush=True)
    print(f"RBOX   : {camera['rbox_name']}", flush=True)
    print(f"SERIAL : {camera['rbox_serial']}", flush=True)
    print(f"CAMARA : {camera['name']}", flush=True)
    print(f"INPUT  : {input_url}", flush=True)
    print(f"OUTPUT : {output_url}", flush=True)
    print("=" * 80, flush=True)

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-rtsp_transport", "tcp",
        "-i", input_url,
        "-c:v", "copy",
        "-an",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        output_url,
    ]

    print("COMANDO:", " ".join(command), flush=True)

    log_path = LOG_DIR / f"rbox_ffmpeg_{camera_id}.log"
    log_file = open(log_path, "a", buffering=1)

    process = subprocess.Popen(
        command,
        stdout=log_file,
        stderr=log_file,
    )

    CAMERA_PROCESSES[camera_id] = process


def cleanup_dead_processes() -> None:
    for camera_id, process in list(CAMERA_PROCESSES.items()):
        if process.poll() is not None:
            print(
                f"FFmpeg muerto para cámara {camera_id}. "
                f"Código salida: {process.returncode}",
                flush=True,
            )
            CAMERA_PROCESSES.pop(camera_id, None)


def stop_camera_push(camera_id: str) -> None:
    process = CAMERA_PROCESSES.get(camera_id)

    if process and process.poll() is None:
        print(f"Deteniendo cámara {camera_id}", flush=True)
        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    CAMERA_PROCESSES.pop(camera_id, None)


def sync_cameras() -> None:
    cleanup_dead_processes()

    cameras = get_rbox_cameras()

    active_camera_ids = {str(camera["id"]) for camera in cameras}

    for camera in cameras:
        start_camera_push(camera)

    for camera_id in list(CAMERA_PROCESSES.keys()):
        if camera_id not in active_camera_ids:
            stop_camera_push(camera_id)


def shutdown_handler(signum, frame):
    print("Apagando servicio RBox...", flush=True)

    for camera_id in list(CAMERA_PROCESSES.keys()):
        stop_camera_push(camera_id)

    db.close()
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    db.open()

    print("Servicio RBox iniciado.", flush=True)

    while True:
        try:
            sync_cameras()

        except DatabaseError as exc:
            print(f"Error BD: {exc}", flush=True)

        except Exception as exc:
            print(f"Error: {exc}", flush=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()