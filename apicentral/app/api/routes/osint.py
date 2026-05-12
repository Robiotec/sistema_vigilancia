from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.osint_service import OsintDataError, OsintService

router = APIRouter(prefix="/osint", tags=["osint"])


_OSINT_SERVICE: OsintService | None = None
_OSINT_SERVICE_PATHS: tuple[str, str] = ("", "")


def _service() -> OsintService:
    global _OSINT_SERVICE, _OSINT_SERVICE_PATHS
    settings = get_settings()
    paths = (settings.osint_geojson, settings.osint_report)
    if _OSINT_SERVICE is None or _OSINT_SERVICE_PATHS != paths:
        _OSINT_SERVICE = OsintService(settings.osint_geojson, settings.osint_report)
        _OSINT_SERVICE_PATHS = paths
    return _OSINT_SERVICE


@router.get("/layers")
def layers(bbox: str = "", limit: int = 2000, layer: str = ""):
    try:
        return _service().layers(bbox, limit, layer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OsintDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/report")
def report():
    try:
        return _service().report()
    except OsintDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
