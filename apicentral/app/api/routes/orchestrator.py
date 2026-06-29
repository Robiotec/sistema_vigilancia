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
from app.models.entities import Camera, Company, RBox, StreamConfig

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


class RBoxCameraPublishConfig(BaseModel):
    camera_id: UUID
    name: str
    unique_code: str
    rtsp_url: str
    mediamtx_path: str
    output_url: str
    output_rtsp_url: str
    channel: int | None = None
    stream_index: int | None = None
    inference_type: str
    updated_at: datetime | None = None


class RBoxCameraConfigResponse(BaseModel):
    ok: bool = True
    generated_at: datetime
    poll_after_seconds: int = 5
    rbox_id: UUID
    rbox_serial: str
    rbox_name: str
    count: int
    items: list[RBoxCameraPublishConfig]


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


def _clean_path(value: Any) -> str:
    return str(value or "").strip().strip("/")


def _output_rtsp_url(path: str, stream: StreamConfig | None, settings: Settings) -> str:
    for candidate in (
        stream.output_rtsp_url if stream else None,
        stream.publish_url if stream else None,
    ):
        value = str(candidate or "").strip()
        if value.startswith("rtsp://"):
            return value
    host = settings.public_host.strip() or "127.0.0.1"
    return f"rtsp://{host}:{settings.mediamtx_rtsp_port}/{path}"


def _stream_configs_by_camera(db: Session, cameras: list[Camera]) -> dict[UUID, StreamConfig]:
    camera_by_id = {camera.id: camera for camera in cameras}
    if not camera_by_id:
        return {}

    rows = db.scalars(
        select(StreamConfig)
        .where(
            StreamConfig.camera_id.in_(camera_by_id),
            StreamConfig.active.is_(True),
            StreamConfig.deleted_at.is_(None),
        )
        .order_by(StreamConfig.created_at)
    ).all()

    exact: dict[UUID, StreamConfig] = {}
    fallback: dict[UUID, StreamConfig] = {}
    for stream in rows:
        camera = camera_by_id.get(stream.camera_id)
        if not camera:
            continue
        stream_path = _clean_path(stream.mediamtx_path)
        camera_path = _clean_path(camera.unique_code)
        if not stream_path:
            continue
        if stream_path == camera_path:
            exact[stream.camera_id] = stream
            continue
        if "/" not in stream_path and stream.camera_id not in fallback:
            fallback[stream.camera_id] = stream
    return {**fallback, **exact}


def _rbox_camera_payload(
    camera: Camera,
    stream: StreamConfig | None,
    settings: Settings,
) -> RBoxCameraPublishConfig:
    path = _clean_path(stream.mediamtx_path if stream else None) or _clean_path(camera.unique_code)
    output_url = _output_rtsp_url(path, stream, settings)
    return RBoxCameraPublishConfig(
        camera_id=camera.id,
        name=camera.name,
        unique_code=_clean_path(camera.unique_code),
        rtsp_url=str(camera.rtsp_url or "").strip(),
        mediamtx_path=path,
        output_url=output_url,
        output_rtsp_url=output_url,
        channel=camera.channel,
        stream_index=camera.stream,
        inference_type=_normalize_inference_type(camera.inference_type),
        updated_at=camera.updated_at,
    )


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
    rbox: str | None = Query(
        default=None,
        description="Filtro opcional por UUID o serial de RBox.",
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
    if rbox:
        normalized_rbox = rbox.strip()
        rbox_filters = [RBox.serial == normalized_rbox]
        try:
            rbox_filters.append(RBox.id == UUID(normalized_rbox))
        except ValueError:
            pass
        rbox_row = db.scalar(
            select(RBox).where(
                or_(*rbox_filters),
                RBox.deleted_at.is_(None),
                RBox.active.is_(True),
            )
        )
        if not rbox_row:
            return OrchestratorInferenceConfigResponse(
                generated_at=datetime.now(timezone.utc),
                inference_types=sorted(INFERENCE_TYPES),
                count=0,
                items=[],
            )
        stmt = stmt.where(Camera.rbox_id == rbox_row.id, Camera.uses_rbox.is_(True))

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
    "/rboxes/{rbox_key}/cameras",
    response_model=RBoxCameraConfigResponse,
    summary="Camaras asociadas a una RBox para publicacion",
    description=(
        "Devuelve las camaras activas que una RBox debe leer localmente y publicar "
        "en el MediaMTX central. `rbox_key` puede ser UUID o serial."
    ),
    dependencies=[Depends(_require_service_token)],
)
def list_rbox_camera_publish_configs(
    rbox_key: str,
    active_only: bool = Query(default=True, description="Excluir camaras inactivas o eliminadas."),
    poll_after_seconds: int = Query(default=5, ge=1, le=300),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RBoxCameraConfigResponse:
    normalized_key = str(rbox_key or "").strip()
    if not normalized_key:
        raise HTTPException(status_code=400, detail="rbox_key_required")

    filters = [RBox.serial == normalized_key]
    try:
        filters.append(RBox.id == UUID(normalized_key))
    except ValueError:
        pass

    rbox = db.scalar(select(RBox).where(or_(*filters), RBox.deleted_at.is_(None)))
    if not rbox:
        raise HTTPException(status_code=404, detail="rbox_not_found")

    now = datetime.now(timezone.utc)
    rbox.last_connection_at = now

    if not rbox.active or str(rbox.status or "").strip().lower() == "inactivo":
        db.commit()
        return RBoxCameraConfigResponse(
            generated_at=now,
            poll_after_seconds=poll_after_seconds,
            rbox_id=rbox.id,
            rbox_serial=rbox.serial,
            rbox_name=rbox.name,
            count=0,
            items=[],
        )

    stmt = (
        select(Camera)
        .where(
            Camera.rbox_id == rbox.id,
            Camera.uses_rbox.is_(True),
            Camera.deleted_at.is_(None),
            Camera.rtsp_url.is_not(None),
            Camera.rtsp_url != "",
            Camera.unique_code.is_not(None),
            Camera.unique_code != "",
            Camera.can_publish.is_(True),
        )
        .order_by(Camera.name)
    )
    if active_only:
        stmt = stmt.where(
            Camera.active.is_(True),
            Camera.status != "inactivo",
        )

    cameras = list(db.scalars(stmt).all())
    stream_by_camera = _stream_configs_by_camera(db, cameras)
    items = [
        _rbox_camera_payload(camera, stream_by_camera.get(camera.id), settings)
        for camera in cameras
    ]

    db.commit()
    return RBoxCameraConfigResponse(
        generated_at=now,
        poll_after_seconds=poll_after_seconds,
        rbox_id=rbox.id,
        rbox_serial=rbox.serial,
        rbox_name=rbox.name,
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
