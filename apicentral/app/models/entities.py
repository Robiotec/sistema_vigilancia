import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ResourceType(str, enum.Enum):
    camera = "camera"
    vehicle = "vehicle"
    drone = "drone"


class TokenAction(str, enum.Enum):
    read = "read"
    publish = "publish"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    ruc: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(180), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company | None] = relationship()
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship()


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserArea(Base):
    __tablename__ = "user_areas"
    __table_args__ = (UniqueConstraint("user_id", "area_id", name="uq_user_area"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    area_id: Mapped[UUID] = mapped_column(ForeignKey("areas.id"), primary_key=True)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_id: Mapped[UUID | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rtsp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rbox_id: Mapped[UUID | None] = mapped_column(ForeignKey("rboxes.id"), nullable=True)
    vehicle_id: Mapped[UUID | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    vehicle_position: Mapped[str | None] = mapped_column(String(120), nullable=True)
    drone_id: Mapped[UUID | None] = mapped_column(ForeignKey("drones.id"), nullable=True)
    unique_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    camera_type: Mapped[str] = mapped_column(String(40), default="fixed")
    inference_type: Mapped[str] = mapped_column(String(40), default="inactiva")
    protocol: Mapped[str] = mapped_column(String(40), default="rtsp")
    ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stream: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[str | None] = mapped_column(String(40), nullable=True)
    public_ip_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    uses_rbox: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="activo")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RBox(Base):
    __tablename__ = "rboxes"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_id: Mapped[UUID | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    serial: Mapped[str] = mapped_column(String(120), unique=True)
    local_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    public_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    server_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    server_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="activo")
    last_connection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_id: Mapped[UUID | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    vehicle_type: Mapped[str] = mapped_column(String(60), default="auto")
    unique_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plate: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_id: Mapped[UUID | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(60), default="robiotec")
    unique_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    drone_type: Mapped[str] = mapped_column(String(60), default="robiotec")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="activo")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StreamPath(Base):
    __tablename__ = "stream_paths"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_id: Mapped[UUID | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    path: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    resource_type: Mapped[ResourceType] = mapped_column(Enum(ResourceType, name="resource_type"))
    resource_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=True)


class StreamTemplate(Base):
    __tablename__ = "stream_templates"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    brand: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    protocol: Mapped[str] = mapped_column(String(40), default="rtsp")
    url_template: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class StreamConfig(Base):
    __tablename__ = "stream_configs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    camera_id: Mapped[UUID | None] = mapped_column(ForeignKey("cameras.id"), nullable=True, index=True)
    drone_id: Mapped[UUID | None] = mapped_column(ForeignKey("drones.id"), nullable=True, index=True)
    input_protocol: Mapped[str] = mapped_column(String(40), default="rtsp")
    origin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    mediamtx_path: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    output_webrtc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_rtsp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_hls_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_path: Mapped[str | None] = mapped_column(String(120), nullable=True)
    publish_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_protocol: Mapped[str] = mapped_column(String(40), default="webrtc")
    mediamtx_server: Mapped[str | None] = mapped_column(String(160), nullable=True)
    mediamtx_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    stream_status: Mapped[str] = mapped_column(String(40), default="pendiente")
    webrtc_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rtsp_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rtmp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_token: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DroneRobiotec(Base):
    __tablename__ = "drone_robiotec_configs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    drone_id: Mapped[UUID] = mapped_column(ForeignKey("drones.id"), unique=True, index=True)
    unique_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_mode: Mapped[str] = mapped_column(String(40), default="api")
    mediamtx_path: Mapped[str] = mapped_column(String(180), unique=True)
    generated_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DroneDJI(Base):
    __tablename__ = "drone_dji_configs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    drone_id: Mapped[UUID] = mapped_column(ForeignKey("drones.id"), unique=True, index=True)
    app_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    app_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_sn: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rtmp_port: Mapped[int] = mapped_column(Integer, default=1935)
    rtmp_path: Mapped[str] = mapped_column(String(180))
    generated_rtmp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StreamAccessToken(Base):
    __tablename__ = "stream_access_tokens"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    stream_path_id: Mapped[UUID] = mapped_column(ForeignKey("stream_paths.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    action: Mapped[TokenAction] = mapped_column(Enum(TokenAction, name="token_action"))
    protocol: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DevicePublishToken(Base):
    __tablename__ = "device_publish_tokens"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    stream_path_id: Mapped[UUID] = mapped_column(ForeignKey("stream_paths.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DroneTelemetry(Base):
    __tablename__ = "drone_telemetry"
    __table_args__ = (Index("ix_drone_telemetry_drone_received_desc", "drone_id", "received_at"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    drone_id: Mapped[UUID | None] = mapped_column(ForeignKey("drones.id"), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    armed_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VehicleTelemetry(Base):
    __tablename__ = "vehicle_telemetry"
    __table_args__ = (Index("ix_vehicle_telemetry_vehicle_received_desc", "vehicle_id", "received_at"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    vehicle_id: Mapped[UUID | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
