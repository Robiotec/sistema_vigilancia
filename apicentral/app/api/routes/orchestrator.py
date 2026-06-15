from __future__ import annotations

from datetime import datetime, timezone
from secrets import compare_digest
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.entities import Camera, Company, StreamConfig

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

INFERENCE_TYPES = {"rostro", "placa", "zona", "movimiento", "inactiva"}


class OrchestratorStreamConfig(BaseModel):
    mediamtx_path: str | None = None
    inference_path: str | None = None
    input_protocol: str | None = None
    output_protocol: str | None = None
    webrtc_enabled: bool = False
    rtsp_enabled: bool = False
    rtmp_enabled: bool = False


class OrchestratorCameraConfig(BaseModel):
    camera_id: UUID
    company_id: UUID
    company_name: str | None = None
    camera_name: str
    unique_code: str | None = None
    camera_type: str
    status: str
    active: bool
    inference_type: str = Field(description="Valores: rostro, placa, zona, movimiento o inactiva.")
    tipo_inferencia: str
    hacer_inferencia: bool
    stop_inference: bool
    stream: OrchestratorStreamConfig
    updated_at: datetime | None = None


class OrchestratorInferenceConfigResponse(BaseModel):
    ok: bool = True
    generated_at: datetime
    poll_after_seconds: int = 5
    inference_types: list[str]
    count: int
    items: list[OrchestratorCameraConfig]


def _require_service_token(
    request: Request,
    x_robiotec_ingest_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.service_ingest_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="service_token_disabled")

    supplied = (x_robiotec_ingest_token or "").strip()
    auth = request.headers.get("Authorization", "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_service_token")


def _inference_path(path: str | None) -> str | None:
    clean = str(path or "").strip().strip("/")
    if not clean:
        return None
    if clean.upper().endswith("/INFERENCE"):
        return clean
    return f"{clean}/INFERENCE"


def _normalize_inference_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in INFERENCE_TYPES else "inactiva"


def _camera_payload(camera: Camera, company: Company | None, stream: StreamConfig | None) -> OrchestratorCameraConfig:
    inference_type = _normalize_inference_type(camera.inference_type)
    active_camera = bool(camera.active and camera.deleted_at is None and str(camera.status or "").lower() != "inactivo")
    should_infer = active_camera and inference_type != "inactiva"
    mediamtx_path = stream.mediamtx_path if stream and stream.active and stream.deleted_at is None else None
    return OrchestratorCameraConfig(
        camera_id=camera.id,
        company_id=camera.company_id,
        company_name=company.name if company else None,
        camera_name=camera.name,
        unique_code=camera.unique_code,
        camera_type=camera.camera_type,
        status=camera.status,
        active=active_camera,
        inference_type=inference_type,
        tipo_inferencia=inference_type,
        hacer_inferencia=should_infer,
        stop_inference=not should_infer,
        stream=OrchestratorStreamConfig(
            mediamtx_path=mediamtx_path,
            inference_path=_inference_path(mediamtx_path),
            input_protocol=stream.input_protocol if stream else None,
            output_protocol=stream.output_protocol if stream else None,
            webrtc_enabled=bool(stream and stream.webrtc_enabled),
            rtsp_enabled=bool(stream and stream.rtsp_enabled),
            rtmp_enabled=bool(stream and stream.rtmp_enabled),
        ),
        updated_at=camera.updated_at,
    )


@router.get(
    "/inference-configs",
    response_model=OrchestratorInferenceConfigResponse,
    summary="Configuracion de inferencia para orquestadores remotos",
    description=(
        "Devuelve el tipo de inferencia que debe ejecutar el orquestador por camara. "
        "Cuando `hacer_inferencia` es false o `inference_type` es `inactiva`, el "
        "orquestador debe detener la inferencia para esa camara."
    ),
    dependencies=[Depends(_require_service_token)],
)
def list_inference_configs(
    camera: str | None = Query(
        default=None,
        description="Filtro opcional por nombre, unique_code o UUID de camara.",
    ),
    only_active: bool = Query(default=True, description="Excluir camaras inactivas o eliminadas."),
    db: Session = Depends(get_db),
) -> OrchestratorInferenceConfigResponse:
    stream_join = and_(
        StreamConfig.camera_id == Camera.id,
        StreamConfig.active.is_(True),
        StreamConfig.deleted_at.is_(None),
    )
    stmt = (
        select(Camera, Company, StreamConfig)
        .join(Company, Company.id == Camera.company_id, isouter=True)
        .join(StreamConfig, stream_join, isouter=True)
        .order_by(Company.name, Camera.name)
    )
    if only_active:
        stmt = stmt.where(Camera.active.is_(True), Camera.deleted_at.is_(None))
    if camera:
        camera_filter = f"%{camera.strip()}%"
        conditions = [
            Camera.name.ilike(camera_filter),
            Camera.unique_code.ilike(camera_filter),
        ]
        try:
            conditions.append(Camera.id == UUID(camera.strip()))
        except ValueError:
            pass
        stmt = stmt.where(or_(*conditions))

    rows = db.execute(stmt).all()
    seen: set[UUID] = set()
    items: list[OrchestratorCameraConfig] = []
    for camera_row, company_row, stream_row in rows:
        if camera_row.id in seen:
            continue
        seen.add(camera_row.id)
        items.append(_camera_payload(camera_row, company_row, stream_row))

    return OrchestratorInferenceConfigResponse(
        generated_at=datetime.now(timezone.utc),
        inference_types=sorted(INFERENCE_TYPES),
        count=len(items),
        items=items,
    )


@router.get(
    "/inference-configs/{camera_key}",
    response_model=OrchestratorCameraConfig,
    summary="Configuracion de inferencia de una camara",
    dependencies=[Depends(_require_service_token)],
)
def get_inference_config(camera_key: str, db: Session = Depends(get_db)) -> OrchestratorCameraConfig:
    configs = list_inference_configs(camera=camera_key, only_active=False, db=db)
    if not configs.items:
        raise HTTPException(status_code=404, detail="camera_not_found")
    return configs.items[0]
