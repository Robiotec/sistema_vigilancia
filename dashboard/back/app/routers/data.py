"""Router de datos geoespaciales: ARCOM, OSINT, tracks de drones y objetivos."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from back.app.context import _text, call_api

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/arcom/concessions")
def arcom_concessions(bbox: str = "", limit: int = 120):
    try:
        return call_api(f"/arcom/concessions?bbox={quote(bbox)}&limit={int(limit or 120)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@router.get("/arcom/concession-lookup")
def arcom_concession_lookup(lat: float, lon: float):
    try:
        return call_api(f"/arcom/concession-lookup?lat={lat}&lon={lon}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "found": False, "concession": None}, status_code=503)


@router.get("/osint/layers")
def osint_layers(bbox: str = "", limit: int = 2000, layer: str = ""):
    try:
        return call_api(f"/osint/layers?bbox={quote(bbox)}&limit={int(limit or 2000)}&layer={quote(layer)}")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "features": []}, status_code=503)


@router.get("/osint/report")
def osint_report():
    try:
        return call_api("/osint/report")
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc), "available": False}, status_code=503)


@router.get("/tracks/drone")
def drone_tracks():
    return {}


@router.post("/tracks/drone/clear")
def drone_tracks_clear():
    return {"ok": True}


@router.get("/objetivos/{objective_id}")
def high_value_objective(objective_id: str):
    return {"id": _text(objective_id), "found": False, "points": []}


@router.post("/objetivos/{objective_id}/clear")
def high_value_objective_clear(objective_id: str):
    return {"id": _text(objective_id), "ok": True}
