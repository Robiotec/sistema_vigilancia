from __future__ import annotations

from pathlib import Path

from django.conf import settings


DASHBOARD_ASSETS = (
    "dashboard/assets/main.css",
    "dashboard/assets/main.js",
)


def dashboard_assets(_request):
    return {"dashboard_asset_version": dashboard_asset_version()}


def dashboard_asset_version() -> str:
    timestamps: list[float] = []
    roots = [
        Path(settings.STATIC_ROOT),
        settings.BASE_DIR / "apps" / "frontend" / "static",
    ]
    for root in roots:
        for relative_path in DASHBOARD_ASSETS:
            path = root / relative_path
            if path.exists():
                timestamps.append(path.stat().st_mtime)
    if not timestamps:
        return "dev"
    return str(int(max(timestamps)))
