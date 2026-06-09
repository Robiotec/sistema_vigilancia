from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from back.app.context import clear_context_cache
from back.app.state import remote_clip_telegram_notifier
from back.app.routers import auth, cameras, data, events, notifications, org, pages, proxy, vehicles
from back.app.routers.cameras import _reload_cam_path_map, start_cam_path_map_refresher

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "front" / "static"
_DASHBOARD_DIR = ROOT  # /root/robiotec/dashboard

app = FastAPI(title="Robiotec Dashboard", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
app.mount("/icons", StaticFiles(directory=STATIC / "icons"), name="icons")

app.add_middleware(GZipMiddleware, minimum_size=1000)


def _worker_loop(module: str, first_delay: int, interval: int, extra: list[str]) -> None:
    """Daemon loop: run a CLI worker module periodically as a subprocess."""
    time.sleep(first_delay)
    while True:
        try:
            subprocess.run(
                [sys.executable, "-m", module, *extra],
                cwd=str(_DASHBOARD_DIR),
                capture_output=True,
                timeout=180,
            )
        except Exception:
            pass
        time.sleep(interval)


@app.middleware("http")
async def invalidate_context_on_write(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        clear_context_cache()
        if "/cameras" in request.url.path or "/rboxes" in request.url.path:
            threading.Thread(target=_reload_cam_path_map, daemon=True).start()
    return response


@app.on_event("startup")
def on_startup() -> None:
    remote_clip_telegram_notifier.start()
    start_cam_path_map_refresher()
    # Ingest events from remote AI server (10.0.0.2) every 5 minutes
    threading.Thread(
        target=_worker_loop,
        args=("back.app.services.remote_event_ingest_worker", 30, 300, ["--limit", "15", "--tail-mb", "8"]),
        daemon=True,
        name="event-ingest",
    ).start()
    # Sync plate vehicle info from 10.0.0.3 every 2 minutes
    threading.Thread(
        target=_worker_loop,
        args=("back.app.services.plate_lookup_sync_worker", 90, 120, ["--limit", "20"]),
        daemon=True,
        name="plate-lookup-sync",
    ).start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    remote_clip_telegram_notifier.stop()


app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(vehicles.router)
app.include_router(notifications.router)
app.include_router(events.router)
app.include_router(org.router)
app.include_router(data.router)
app.include_router(proxy.router)  # catch-all — debe ir último
