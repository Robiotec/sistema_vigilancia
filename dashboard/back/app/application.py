from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from back.app.context import clear_context_cache
from back.app.routers import auth, cameras, data, events, notifications, org, pages, proxy, reports, vehicles
from back.app.routers.cameras import _reload_cam_path_map, start_cam_path_map_refresher
from back.app.services.db_telegram_feeder import DBTelegramFeeder
from back.app.services.artemis import ArtemisTracker
from back.app.services.fleet_daily_report import FleetDailyReportWorker

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "front" / "static"
STATIC_ASSETS = STATIC / "assets"
STATIC_ICONS = STATIC / "icons"
if not STATIC_ASSETS.exists():
    STATIC_ASSETS = STATIC / "src" / "assets"
if not STATIC_ICONS.exists():
    STATIC_ICONS = STATIC / "src" / "icons"
_DASHBOARD_DIR = ROOT  # /root/robiotec/dashboard

_telegram_feeder: DBTelegramFeeder | None = None
_artemis_tracker: ArtemisTracker | None = None
_fleet_report_worker: FleetDailyReportWorker | None = None

app = FastAPI(title="Robiotec Dashboard", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/assets", StaticFiles(directory=STATIC_ASSETS), name="assets")
app.mount("/icons", StaticFiles(directory=STATIC_ICONS), name="icons")

app.add_middleware(GZipMiddleware, minimum_size=1000)


_CACHE_DIRS = [
    Path(__file__).resolve().parent / "data" / "event_videos",
    Path(__file__).resolve().parent / "data" / "telegram_clip_crops",
]


def _cleanup_cache(max_age_days: int) -> None:
    cutoff = time.time() - max_age_days * 86400
    total_files = 0
    total_bytes = 0
    for directory in _CACHE_DIRS:
        if not directory.exists():
            continue
        for f in directory.iterdir():
            if not f.is_file():
                continue
            try:
                st = f.stat()
                if st.st_mtime < cutoff:
                    size = st.st_size
                    f.unlink()
                    total_files += 1
                    total_bytes += size
            except Exception:
                pass
    if total_files:
        logger.info("Cache cleanup: %d archivos eliminados (%.1f MB)", total_files, total_bytes / 1_048_576)


def _daily_cache_cleanup_loop(max_age_days: int) -> None:
    time.sleep(3600)  # espera 1h al arranque antes del primer ciclo
    while True:
        try:
            _cleanup_cache(max_age_days)
        except Exception:
            pass
        time.sleep(86400)  # cada 24h


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
    global _telegram_feeder, _artemis_tracker, _fleet_report_worker
    for directory in _CACHE_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
    start_cam_path_map_refresher()
    from back.app.config import get_settings
    app_settings = get_settings()
    if app_settings.plate_lookup_embedded_worker_enabled:
        threading.Thread(
            target=_worker_loop,
            args=("back.app.services.plate_lookup_sync_worker", 90, 120, ["--limit", "20"]),
            daemon=True,
            name="plate-lookup-sync",
        ).start()
    # Telegram feeder: lee camera_event_history (DB local) -> outbox -> Telegram
    _telegram_feeder = DBTelegramFeeder(app_settings)
    _telegram_feeder.start()
    # Artemis fleet tracker: extrae posiciones de theo.24hm.net → telemetría
    _artemis_tracker = ArtemisTracker()
    _artemis_tracker.start()
    # Reporte diario PDF de flota: usa la misma configuracion SMTP de alertas
    _fleet_report_worker = FleetDailyReportWorker()
    _fleet_report_worker.start()
    # Limpieza diaria de cache local (videos y crops descargados desde MinIO)
    threading.Thread(
        target=_daily_cache_cleanup_loop,
        args=(app_settings.cache_max_age_days,),
        daemon=True,
        name="cache-cleanup",
    ).start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    global _telegram_feeder, _artemis_tracker, _fleet_report_worker
    if _telegram_feeder:
        _telegram_feeder.stop()
    if _artemis_tracker:
        _artemis_tracker.stop()
    if _fleet_report_worker:
        _fleet_report_worker.stop()


app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(vehicles.router)
app.include_router(notifications.router)
app.include_router(events.router)
app.include_router(org.router)
app.include_router(data.router)
app.include_router(reports.router)
app.include_router(proxy.router)  # catch-all — debe ir último
