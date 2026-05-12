from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.arcom_service import ArcomDataError, ArcomService

router = APIRouter(prefix="/arcom", tags=["arcom"])


_ARCOM_SERVICE: ArcomService | None = None
_ARCOM_SERVICE_PATH = ""


def _service() -> ArcomService:
    global _ARCOM_SERVICE, _ARCOM_SERVICE_PATH
    path = get_settings().arcom_geojson
    if _ARCOM_SERVICE is None or _ARCOM_SERVICE_PATH != path:
        _ARCOM_SERVICE = ArcomService(path)
        _ARCOM_SERVICE_PATH = path
    return _ARCOM_SERVICE


@router.get("/concessions")
def concessions(bbox: str = "", limit: int = 120):
    try:
        return _service().concessions(bbox, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ArcomDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/concession-lookup")
def concession_lookup(lat: float, lon: float):
    try:
        return _service().concession_lookup(lat, lon)
    except ArcomDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
