from typing import Any
from urllib.parse import quote
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.security import hash_password
from app.db.session import get_db
from app.models.entities import (
    Area,
    Camera,
    Company,
    Drone,
    DroneDJI,
    DroneRobiotec,
    DroneTelemetry,
    RBox,
    Role,
    ResourceType,
    StreamConfig,
    StreamPath,
    StreamTemplate,
    User,
    UserRole,
    Vehicle,
    VehicleTelemetry,
    utcnow,
)
from app.schemas.common import MessageResponse
from app.schemas.stream import StreamPathCreate
from app.services.auth_service import get_user_roles

router = APIRouter(tags=["admin"])
CAMERA_INFERENCE_TYPES = {"rostros", "placas", "zonas", "movimientos", "inactiva"}


class CompanyCreate(BaseModel):
    name: str
    ruc: str | None = None
    address: str | None = None
    active: bool = True


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    active: bool = True


class UserCreate(BaseModel):
    username: str
    password: str
    company_id: UUID | None = None
    name: str | None = None
    email: str | None = None
    active: bool = True
    role_names: list[str] = Field(default_factory=lambda: ["viewer"])


class AreaCreate(BaseModel):
    company_id: UUID
    name: str
    active: bool = True


class CameraCreate(BaseModel):
    company_id: UUID
    area_id: UUID | None = None
    rbox_id: UUID | None = None
    vehicle_id: UUID | None = None
    vehicle_position: str | None = None
    drone_id: UUID | None = None
    name: str
    brand: str
    model: str | None = None
    rtsp_url: str | None = None
    unique_code: str | None = None
    camera_type: str = "fixed"
    inference_type: str = "inactiva"
    protocol: str = "rtsp"
    ip: str | None = None
    port: int | None = None
    username: str | None = None
    password_encrypted: str | None = None
    channel: int | None = None
    stream: int | None = None
    quality: str | None = None
    public_ip_enabled: bool = False
    uses_rbox: bool = False
    status: str = "activo"
    active: bool = True
    can_publish: bool = True


class RBoxCreate(BaseModel):
    company_id: UUID
    area_id: UUID | None = None
    name: str
    serial: str | None = None
    local_ip: str | None = None
    public_ip: str | None = None
    server_ip: str | None = None
    server_port: int | None = None
    location: str | None = None
    status: str = "activo"
    active: bool = True


class VehicleCreate(BaseModel):
    company_id: UUID
    area_id: UUID | None = None
    owner_user_id: UUID | None = None
    name: str
    vehicle_type: str = "auto"
    unique_code: str | None = None
    plate: str | None = None
    model: str | None = None
    description: str | None = None
    active: bool = True
    can_publish: bool = True


class DroneCameraCreate(CameraCreate):
    company_id: UUID | None = None
    drone_id: UUID | None = None


class DroneCreate(BaseModel):
    company_id: UUID
    area_id: UUID | None = None
    owner_user_id: UUID | None = None
    name: str
    provider: str = "robiotec"
    unique_code: str | None = None
    drone_type: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    status: str = "activo"
    public_ip: str | None = None
    rtmp_port: int = 1935
    rtmp_path: str | None = None
    unique_ip: str | None = None
    cameras: list[DroneCameraCreate] = Field(default_factory=list)
    active: bool = True
    can_publish: bool = True


class StreamTemplateCreate(BaseModel):
    brand: str
    model: str | None = None
    protocol: str = "rtsp"
    url_template: str
    description: str | None = None


class StreamConfigCreate(BaseModel):
    camera_id: UUID | None = None
    drone_id: UUID | None = None
    input_protocol: str = "rtsp"
    origin_url: str | None = None
    mediamtx_path: str
    output_webrtc_url: str | None = None
    output_rtsp_url: str | None = None
    output_hls_url: str | None = None
    publish_path: str | None = None
    publish_url: str | None = None
    output_protocol: str = "webrtc"
    mediamtx_server: str | None = None
    mediamtx_port: int | None = None
    token_encrypted: str | None = None
    stream_status: str = "pendiente"
    webrtc_enabled: bool = True
    rtsp_enabled: bool = True
    rtmp_enabled: bool = False
    active: bool = True
    requires_token: bool = True


def require_admin(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    roles = set(get_user_roles(db, current_user))
    if not roles.intersection({"master", "admin", "company_admin"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
    return current_user


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "stream"


def _generated_code(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}".upper()


def _normalize_brand(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "")


def _build_rtsp_url(data: dict[str, Any], raw_password: str | None = None) -> str | None:
    brand = _normalize_brand(data.get("brand"))
    if brand not in {"dahua", "hikvision"}:
        return data.get("rtsp_url")
    ip = (data.get("ip") or "").strip()
    if not ip:
        return data.get("rtsp_url")
    user = (data.get("username") or "").strip()
    password = (raw_password or "").strip()
    port = int(data.get("port") or 554)
    channel = int(data.get("channel") or 1)
    quality = (data.get("quality") or "mainstream").strip().lower()
    stream = data.get("stream")
    subtype = int(stream) if stream is not None else (1 if quality == "substream" else 0)
    auth = f"{quote(user)}:{quote(password)}@" if user or password else ""
    if brand == "hikvision":
        suffix = "02" if quality == "substream" or subtype == 1 else "01"
        hikvision_channel = channel if channel >= 100 else int(f"{channel}{suffix}")
        path = f"Streaming/Channels/{hikvision_channel}"
    else:
        path = f"cam/realmonitor?channel={channel}&subtype={1 if quality == 'substream' or subtype == 1 else 0}"
    return f"rtsp://{auth}{ip}:{port}/{path}"


def _stream_urls(path: str) -> dict[str, str]:
    settings = get_settings()
    public_host = settings.public_host or "127.0.0.1"
    rtsp_port = settings.mediamtx_rtsp_port
    return {
        "output_webrtc_url": f"/stream/token/{path}",
        "output_rtsp_url": f"rtsp://{public_host}:{rtsp_port}/{path}",
        "output_hls_url": f"/{path}/index.m3u8",
        "publish_path": path,
        "publish_url": f"rtsp://{public_host}:{rtsp_port}/{path}",
        "mediamtx_server": public_host,
        "mediamtx_port": rtsp_port,
    }


def _ensure_stream_for_resource(
    db: Session,
    *,
    company_id: UUID,
    area_id: UUID | None,
    resource_type: ResourceType,
    resource_id: UUID,
    path: str,
    origin_url: str | None,
    input_protocol: str,
    can_publish: bool = True,
) -> None:
    path = _slug(path)
    stream_url_fields = _stream_urls(path)
    existing_path = db.scalar(select(StreamPath).where(StreamPath.path == path))
    if not existing_path:
        db.add(
            StreamPath(
                company_id=company_id,
                area_id=area_id,
                path=path,
                resource_type=resource_type,
                resource_id=resource_id,
                active=True,
                can_publish=can_publish,
            )
        )
    existing_config = db.scalar(select(StreamConfig).where(StreamConfig.mediamtx_path == path))
    if not existing_config:
        db.add(
            StreamConfig(
                camera_id=resource_id if resource_type == ResourceType.camera else None,
                drone_id=resource_id if resource_type == ResourceType.drone else None,
                input_protocol=input_protocol,
                origin_url=origin_url,
                mediamtx_path=path,
                output_protocol="webrtc",
                stream_status="pendiente",
                webrtc_enabled=True,
                rtsp_enabled=True,
                rtmp_enabled=input_protocol == "rtmp",
                **stream_url_fields,
            )
        )
    else:
        existing_config.origin_url = origin_url
        existing_config.input_protocol = input_protocol
        existing_config.camera_id = resource_id if resource_type == ResourceType.camera else existing_config.camera_id
        existing_config.drone_id = resource_id if resource_type == ResourceType.drone else existing_config.drone_id
        existing_config.output_protocol = existing_config.output_protocol or "webrtc"
        existing_config.rtmp_enabled = input_protocol == "rtmp"
        for key, value in stream_url_fields.items():
            setattr(existing_config, key, value)


def _prepare_camera_data(data: dict[str, Any], existing: Camera | None = None) -> dict[str, Any]:
    if existing:
        # unique_code/id_unico es el publish path estable de MediaMTX.
        # Cambiarlo durante una edicion rompe URLs, StreamConfig y StreamPath.
        data["unique_code"] = existing.unique_code
    if not data.get("unique_code"):
        data["unique_code"] = existing.unique_code if existing and existing.unique_code else _generated_code("CAM")
    data["brand"] = data.get("brand") or "custom"
    data["protocol"] = data.get("protocol") or "rtsp"
    data["inference_type"] = data.get("inference_type") or "inactiva"
    if data["inference_type"] not in CAMERA_INFERENCE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de inferencia invalido")
    raw_password = data.get("password_encrypted")
    if raw_password and str(raw_password).startswith("fernet:"):
        raw_password = decrypt_secret(raw_password)
    if not raw_password and existing:
        raw_password = decrypt_secret(existing.password_encrypted)
    if data.get("rbox_id"):
        data["uses_rbox"] = True
    if _normalize_brand(data.get("brand")) in {"dahua", "hikvision"}:
        data["port"] = data.get("port") or 554
        data["channel"] = data.get("channel") or 1
        data["quality"] = data.get("quality") or ("substream" if data.get("stream") == 1 else "mainstream")
        data["stream"] = data.get("stream") if data.get("stream") is not None else (1 if data["quality"] == "substream" else 0)
        data["rtsp_url"] = _build_rtsp_url(data, raw_password)
    if data.get("password_encrypted"):
        data["password_encrypted"] = encrypt_secret(data.get("password_encrypted"))
    return data


def _coerce_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _ensure_camera_company_consistency(db: Session, data: dict[str, Any]) -> None:
    company_id = _coerce_uuid(data.get("company_id"))
    data["company_id"] = company_id
    for key, model in (("rbox_id", RBox), ("vehicle_id", Vehicle), ("drone_id", Drone)):
        value = _coerce_uuid(data.get(key))
        data[key] = value
        if not value:
            continue
        item = db.get(model, value)
        if not item:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} no existe")
        if item.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} pertenece a otra empresa")


def _create_camera_with_stream(db: Session, data: dict[str, Any]) -> Camera:
    _ensure_camera_company_consistency(db, data)
    camera_data = _prepare_camera_data(data)
    item = Camera(**camera_data)
    db.add(item)
    db.flush()
    path = item.unique_code or item.name
    _ensure_stream_for_resource(
        db,
        company_id=item.company_id,
        area_id=item.area_id,
        resource_type=ResourceType.camera,
        resource_id=item.id,
        path=path,
        origin_url=item.rtsp_url,
        input_protocol=item.protocol or "rtsp",
        can_publish=item.can_publish,
    )
    return item


def crud_routes(prefix: str, model, create_schema):
    local_router = APIRouter(prefix=prefix, dependencies=[Depends(require_admin)])

    @local_router.get("")
    def list_items(db: Session = Depends(get_db)):
        query = select(model)
        if hasattr(model, "deleted_at"):
            query = query.where(model.deleted_at.is_(None))
        return db.scalars(query).all()

    @local_router.get("/{item_id}")
    def get_item(item_id: UUID, db: Session = Depends(get_db)):
        item = db.get(model, item_id)
        if not item or (hasattr(item, "deleted_at") and item.deleted_at is not None):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
        return item

    @local_router.put("/{item_id}")
    def update_item(item_id: UUID, payload: dict[str, Any], db: Session = Depends(get_db)):
        item = db.get(model, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
        drone_extra = {}
        if model is Drone:
            drone_extra = {
                "public_ip": payload.pop("public_ip", None),
                "rtmp_port": payload.pop("rtmp_port", None),
                "rtmp_path": payload.pop("rtmp_path", None),
                "unique_ip": payload.pop("unique_ip", None),
            }
            if payload.get("drone_type") is None and payload.get("provider"):
                payload["drone_type"] = payload.get("provider")
        if model is Camera:
            payload = _prepare_camera_data(payload, item)
            payload["company_id"] = payload.get("company_id") or item.company_id
            _ensure_camera_company_consistency(db, payload)
        for key, value in payload.items():
            if key == "id" or not hasattr(item, key):
                continue
            setattr(item, key, value)
        if model is Camera:
            path = item.unique_code or item.name
            _ensure_stream_for_resource(
                db,
                company_id=item.company_id,
                area_id=item.area_id,
                resource_type=ResourceType.camera,
                resource_id=item.id,
                path=path,
                origin_url=item.rtsp_url,
                input_protocol=item.protocol or "rtsp",
                can_publish=item.can_publish,
            )
        if model is Drone:
            provider = (item.provider or item.drone_type or "robiotec").lower()
            path = item.unique_code or item.name
            stream_config = db.scalar(select(StreamConfig).where(StreamConfig.drone_id == item.id))
            if provider == "dji":
                settings = get_settings()
                rtmp_path = drone_extra.get("rtmp_path") or item.unique_code or _slug(path)
                port = drone_extra.get("rtmp_port") or settings.mediamtx_rtmp_port
                public_ip = drone_extra.get("public_ip") or settings.public_host
                generated_url = f"rtmp://{public_ip}:{port}/{rtmp_path}"
                dji_config = db.scalar(select(DroneDJI).where(DroneDJI.drone_id == item.id))
                if dji_config:
                    dji_config.public_ip = public_ip
                    dji_config.rtmp_port = port
                    dji_config.rtmp_path = rtmp_path
                    dji_config.generated_rtmp_url = generated_url
                else:
                    db.add(DroneDJI(drone_id=item.id, public_ip=public_ip, rtmp_port=port, rtmp_path=rtmp_path, generated_rtmp_url=generated_url))
                if stream_config:
                    stream_config.origin_url = generated_url
                    stream_config.input_protocol = "rtmp"
                    stream_config.mediamtx_path = rtmp_path
            else:
                mediamtx_path = item.unique_code or _slug(path)
                robiotec_config = db.scalar(select(DroneRobiotec).where(DroneRobiotec.drone_id == item.id))
                if robiotec_config:
                    robiotec_config.unique_ip = drone_extra.get("unique_ip") or robiotec_config.unique_ip
                    robiotec_config.mediamtx_path = mediamtx_path
                    robiotec_config.generated_url = f"/{mediamtx_path}"
                else:
                    db.add(DroneRobiotec(drone_id=item.id, unique_ip=drone_extra.get("unique_ip"), mediamtx_path=mediamtx_path, generated_url=f"/{mediamtx_path}"))
                if stream_config:
                    stream_config.mediamtx_path = mediamtx_path
                    stream_config.input_protocol = "webrtc"
        db.commit()
        db.refresh(item)
        return item

    @local_router.post("")
    def create_item(payload: create_schema, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        data = payload.model_dump()
        if model is User:
            role_names = data.pop("role_names")
            data["password_hash"] = hash_password(data.pop("password"))
            data["name"] = data.get("name") or data.get("username")
        drone_extra = {}
        if model is Drone:
            cameras = data.pop("cameras", [])
            if data.get("active", True) and not cameras:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Todo dron activo debe crearse con al menos una camara asociada",
                )
            drone_extra = {
                "public_ip": data.pop("public_ip", None),
                "rtmp_port": data.pop("rtmp_port", 1935),
                "rtmp_path": data.pop("rtmp_path", None),
                "unique_ip": data.pop("unique_ip", None),
            }
            data["drone_type"] = data.get("drone_type") or data.get("provider") or "robiotec"
        if model is Camera:
            item = _create_camera_with_stream(db, data)
            db.commit()
            db.refresh(item)
            return item
        if model is RBox and not data.get("serial"):
            data["serial"] = _generated_code("RBOX")
        item = model(**data)
        db.add(item)
        db.flush()
        if model is User:
            roles = db.scalars(select(Role).where(Role.name.in_(role_names))).all()
            if len(roles) != len(set(role_names)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol invalido")
            for role in roles:
                db.add(UserRole(user_id=item.id, role_id=role.id))
        if model is Camera:
            path = data.get("unique_code") or data.get("name")
            if data.get("rtsp_url") or data.get("can_publish"):
                _ensure_stream_for_resource(
                    db,
                    company_id=item.company_id,
                    area_id=item.area_id,
                    resource_type=ResourceType.camera,
                    resource_id=item.id,
                    path=path,
                    origin_url=item.rtsp_url,
                    input_protocol=item.protocol or "rtsp",
                    can_publish=item.can_publish,
                )
        if model is Drone:
            provider = (item.provider or item.drone_type or "robiotec").lower()
            path = data.get("unique_code") or _generated_code("DRON")
            if not item.unique_code:
                item.unique_code = _slug(path).upper()
                path = item.unique_code
            if provider == "dji":
                rtmp_path = drone_extra.get("rtmp_path") or _slug(path)
                settings = get_settings()
                port = drone_extra.get("rtmp_port") or settings.mediamtx_rtmp_port
                public_ip = drone_extra.get("public_ip") or settings.public_host
                generated_url = f"rtmp://{public_ip}:{port}/{rtmp_path}"
                db.add(
                    DroneDJI(
                        drone_id=item.id,
                        public_ip=public_ip,
                        rtmp_port=port,
                        rtmp_path=rtmp_path,
                        generated_rtmp_url=generated_url,
                    )
                )
                origin_url = generated_url if public_ip else None
                input_protocol = "rtmp"
            else:
                mediamtx_path = _slug(path)
                db.add(
                    DroneRobiotec(
                        drone_id=item.id,
                        unique_ip=drone_extra.get("unique_ip"),
                        mediamtx_path=mediamtx_path,
                        generated_url=f"/{mediamtx_path}",
                    )
                )
                origin_url = None
                input_protocol = "webrtc"
            for camera_payload in cameras:
                camera_data = dict(camera_payload)
                camera_data["company_id"] = item.company_id
                camera_data["drone_id"] = item.id
                camera_data["camera_type"] = camera_data.get("camera_type") or "drone"
                camera_data["unique_code"] = camera_data.get("unique_code") or item.unique_code
                camera_data["protocol"] = camera_data.get("protocol") or input_protocol
                camera_data["brand"] = camera_data.get("brand") or provider
                _create_camera_with_stream(db, camera_data)
        db.commit()
        db.refresh(item)
        return item

    @local_router.delete("/{item_id}", response_model=MessageResponse)
    def delete_item(item_id: UUID, db: Session = Depends(get_db)) -> MessageResponse:
        item = db.get(model, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
        now = utcnow()
        if model is Camera:
            for stream_config in db.scalars(select(StreamConfig).where(StreamConfig.camera_id == item_id)).all():
                stream_config.active = False
                stream_config.deleted_at = now
            for stream_path in db.scalars(select(StreamPath).where(StreamPath.resource_id == item_id)).all():
                stream_path.active = False
        if model is Drone:
            for camera in db.scalars(select(Camera).where(Camera.drone_id == item_id)).all():
                camera.active = False
                camera.deleted_at = now
                for stream_config in db.scalars(select(StreamConfig).where(StreamConfig.camera_id == camera.id)).all():
                    stream_config.active = False
                    stream_config.deleted_at = now
            for stream_path in db.scalars(select(StreamPath).where(StreamPath.resource_id == item_id)).all():
                stream_path.active = False
            for config_model in (DroneRobiotec, DroneDJI):
                config = db.scalar(select(config_model).where(config_model.drone_id == item_id))
                if config and hasattr(config, "active"):
                    config.active = False
        if model is Vehicle:
            for stream_path in db.scalars(select(StreamPath).where(StreamPath.resource_id == item_id)).all():
                stream_path.active = False
        if hasattr(item, "active"):
            item.active = False
        if hasattr(item, "deleted_at"):
            item.deleted_at = now
        else:
            db.delete(item)
        db.commit()
        return MessageResponse(message="Recurso eliminado")

    return local_router


@router.get("/rboxes/{rbox_id}/cameras")
def list_rbox_cameras(rbox_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    rbox = db.get(RBox, rbox_id)
    if not rbox:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RBox no encontrada")
    cameras = db.scalars(
        select(Camera).where(Camera.rbox_id == rbox_id, Camera.active.is_(True))
    ).all()
    return [
        {
            "id": camera.id,
            "name": camera.name,
            "unique_code": camera.unique_code,
            "brand": camera.brand,
            "rtsp_url": camera.rtsp_url,
            "ip": camera.ip,
            "port": camera.port,
            "channel": camera.channel,
            "quality": camera.quality,
            "mediamtx_path": _slug(camera.unique_code or camera.name),
            "can_publish": camera.can_publish,
        }
        for camera in cameras
    ]


router.include_router(crud_routes("/companies", Company, CompanyCreate))
router.include_router(crud_routes("/roles", Role, RoleCreate))
router.include_router(crud_routes("/users", User, UserCreate))
router.include_router(crud_routes("/areas", Area, AreaCreate))
router.include_router(crud_routes("/cameras", Camera, CameraCreate))
router.include_router(crud_routes("/rboxes", RBox, RBoxCreate))
router.include_router(crud_routes("/vehicles", Vehicle, VehicleCreate))
router.include_router(crud_routes("/drones", Drone, DroneCreate))
router.include_router(crud_routes("/stream-paths", StreamPath, StreamPathCreate))
router.include_router(crud_routes("/stream-templates", StreamTemplate, StreamTemplateCreate))
router.include_router(crud_routes("/stream-configs", StreamConfig, StreamConfigCreate))
