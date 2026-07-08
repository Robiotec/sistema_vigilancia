from __future__ import annotations

import base64
import hashlib
import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.services import ServiceResult
from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.streaming.models import StreamConfig, StreamPath


@dataclass(frozen=True)
class CameraPublishConfig:
    camera_id: str
    path: str
    rtsp_url: str
    uses_rbox: bool


class CameraCatalogService:
    def list_rbox_cameras(self, rbox_serial: str) -> list[Camera]:
        return list(
            Camera.objects.filter(rbox__serial=rbox_serial)
            .select_related("rbox")
            .order_by("name")
        )

    def build_publish_configs(self, rbox_serial: str) -> ServiceResult[list[CameraPublishConfig]]:
        cameras = self.list_rbox_cameras(rbox_serial)
        configs: list[CameraPublishConfig] = []

        for camera in cameras:
            path = camera.unique_code or str(camera.id)
            if not camera.rtsp_url:
                continue
            configs.append(
                CameraPublishConfig(
                    camera_id=str(camera.id),
                    path=path,
                    rtsp_url=camera.rtsp_url,
                    uses_rbox=camera.uses_rbox,
                )
            )

        return ServiceResult.success(configs)


class RBoxRegistryService:
    def touch(self, serial: str) -> ServiceResult[RBox]:
        try:
            rbox = RBox.objects.get(serial=serial)
        except RBox.DoesNotExist:
            return ServiceResult.failure("RBox no registrada")
        return ServiceResult.success(rbox)


class DeviceAdminError(ValueError):
    pass


class SecretCipher:
    def __init__(self, raw_key: str | None = None):
        self.raw_key = raw_key or settings.ROBIOTEC_FIELD_ENCRYPTION_KEY or settings.SECRET_KEY

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith("fernet:"):
            return value
        token = self._fernet().encrypt(value.encode("utf-8")).decode("utf-8")
        return f"fernet:{token}"

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        if not value.startswith("fernet:"):
            return value
        try:
            return self._fernet().decrypt(value.removeprefix("fernet:").encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return None

    def _fernet(self) -> Fernet:
        try:
            key = self.raw_key.encode("utf-8")
            if len(key) == 44:
                return Fernet(key)
        except Exception:
            pass
        digest = hashlib.sha256(self.raw_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in str(value or "").strip())
    return "-".join(part for part in cleaned.split("-") if part) or "stream"


def generated_code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}".upper()


def normalize_brand(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "")


def stream_urls(path: str) -> dict[str, object]:
    public_host = settings.ROBIOTEC_PUBLIC_HOST or "127.0.0.1"
    rtsp_port = settings.MEDIAMTX_RTSP_PORT
    return {
        "output_webrtc_url": f"/stream/token/{path}",
        "output_rtsp_url": f"rtsp://{public_host}:{rtsp_port}/{path}",
        "output_hls_url": f"/{path}/index.m3u8",
        "publish_path": path,
        "publish_url": f"rtsp://{public_host}:{rtsp_port}/{path}",
        "mediamtx_server": public_host,
        "mediamtx_port": rtsp_port,
    }


def drone_stream_urls(path: str) -> dict[str, object]:
    public_host = settings.ROBIOTEC_PUBLIC_HOST or "127.0.0.1"
    rtsp_port = settings.MEDIAMTX_RTSP_PORT
    rtmp_port = int(getattr(settings, "MEDIAMTX_RTMP_PORT", 1935) or 1935)
    return {
        "output_webrtc_url": f"/stream/token/{path}",
        "output_rtsp_url": f"rtsp://{public_host}:{rtsp_port}/{path}",
        "output_hls_url": f"/{path}/index.m3u8",
        "publish_path": path,
        "publish_url": f"rtmp://{public_host}:{rtmp_port}/{path}",
        "mediamtx_server": public_host,
        "mediamtx_port": rtmp_port,
    }


class StreamProvisioningService:
    def ensure_camera_stream(self, camera: Camera) -> None:
        path = slug(camera.unique_code or camera.name)
        url_fields = stream_urls(path)

        stream_path, _ = StreamPath.objects.get_or_create(
            path=path,
            defaults={
                "company_id": camera.company_id,
                "area_id": camera.area_id,
                "resource_type": "camera",
                "resource_id": camera.id,
                "active": True,
                "can_publish": camera.can_publish,
            },
        )
        changed_path_fields = {
            "company_id": camera.company_id,
            "area_id": camera.area_id,
            "resource_type": "camera",
            "resource_id": camera.id,
            "active": True,
            "can_publish": camera.can_publish,
        }
        for field, value in changed_path_fields.items():
            setattr(stream_path, field, value)
        stream_path.save()

        stream_config, _ = StreamConfig.all_objects.get_or_create(
            mediamtx_path=path,
            defaults={
                "camera_id": camera.id,
                "input_protocol": camera.protocol or "rtsp",
                "origin_url": camera.rtsp_url,
                "output_protocol": "webrtc",
                "stream_status": "pendiente",
                "webrtc_enabled": True,
                "rtsp_enabled": True,
                "rtmp_enabled": False,
                "requires_token": True,
                "active": True,
                **url_fields,
            },
        )
        stream_config.camera_id = camera.id
        stream_config.input_protocol = camera.protocol or "rtsp"
        stream_config.origin_url = camera.rtsp_url
        stream_config.output_protocol = stream_config.output_protocol or "webrtc"
        stream_config.stream_status = stream_config.stream_status or "pendiente"
        stream_config.webrtc_enabled = True
        stream_config.rtsp_enabled = True
        stream_config.rtmp_enabled = False
        stream_config.active = True
        stream_config.deleted_at = None
        for field, value in url_fields.items():
            setattr(stream_config, field, value)
        stream_config.save()

    def disable_camera_stream(self, camera: Camera) -> None:
        now = timezone.now()
        StreamConfig.all_objects.filter(camera_id=camera.id).update(active=False, deleted_at=now)
        StreamPath.objects.filter(resource_type="camera", resource_id=camera.id).update(active=False)

    def ensure_drone_stream(self, drone: Drone) -> None:
        path = slug(drone.unique_code or drone.name)
        url_fields = drone_stream_urls(path)

        stream_path, _ = StreamPath.objects.get_or_create(
            path=path,
            defaults={
                "company_id": drone.company_id,
                "area_id": drone.area_id,
                "resource_type": "drone",
                "resource_id": drone.id,
                "active": True,
                "can_publish": drone.can_publish,
            },
        )
        changed_path_fields = {
            "company_id": drone.company_id,
            "area_id": drone.area_id,
            "resource_type": "drone",
            "resource_id": drone.id,
            "active": True,
            "can_publish": drone.can_publish,
        }
        for field, value in changed_path_fields.items():
            setattr(stream_path, field, value)
        stream_path.save()

        stream_config, _ = StreamConfig.all_objects.get_or_create(
            mediamtx_path=path,
            defaults={
                "drone_id": drone.id,
                "input_protocol": "rtmp",
                "origin_url": url_fields["publish_url"],
                "output_protocol": "webrtc",
                "stream_status": "pendiente",
                "webrtc_enabled": True,
                "rtsp_enabled": True,
                "rtmp_enabled": True,
                "requires_token": True,
                "active": True,
                **url_fields,
            },
        )
        stream_config.drone_id = drone.id
        stream_config.input_protocol = "rtmp"
        stream_config.origin_url = str(url_fields["publish_url"])
        stream_config.output_protocol = stream_config.output_protocol or "webrtc"
        stream_config.stream_status = stream_config.stream_status or "pendiente"
        stream_config.webrtc_enabled = True
        stream_config.rtsp_enabled = True
        stream_config.rtmp_enabled = True
        stream_config.active = True
        stream_config.deleted_at = None
        for field, value in url_fields.items():
            setattr(stream_config, field, value)
        stream_config.save()

    def disable_drone_stream(self, drone: Drone) -> None:
        now = timezone.now()
        StreamConfig.all_objects.filter(drone_id=drone.id).update(active=False, deleted_at=now)
        StreamPath.objects.filter(resource_type="drone", resource_id=drone.id).update(active=False)


class CameraAdminService:
    inference_types = {"rostro", "placa", "zona", "movimiento", "inactiva"}

    def __init__(
        self,
        cipher: SecretCipher | None = None,
        streams: StreamProvisioningService | None = None,
    ):
        self.cipher = cipher or SecretCipher()
        self.streams = streams or StreamProvisioningService()

    @transaction.atomic
    def create(self, data: dict, *, raw_password: str | None = None) -> Camera:
        camera = Camera(**self._prepare(data, raw_password=raw_password))
        camera.save()
        self.streams.ensure_camera_stream(camera)
        return camera

    @transaction.atomic
    def update(self, camera: Camera, data: dict, *, raw_password: str | None = None) -> Camera:
        prepared = self._prepare(data, existing=camera, raw_password=raw_password)
        for field, value in prepared.items():
            setattr(camera, field, value)
        camera.save()
        if camera.active:
            self.streams.ensure_camera_stream(camera)
        else:
            self.streams.disable_camera_stream(camera)
        return camera

    @transaction.atomic
    def delete(self, camera: Camera) -> None:
        camera.active = False
        camera.deleted_at = timezone.now()
        camera.save(update_fields=["active", "deleted_at"])
        self.streams.disable_camera_stream(camera)

    def _prepare(
        self,
        data: dict,
        *,
        existing: Camera | None = None,
        raw_password: str | None = None,
    ) -> dict:
        prepared = dict(data)
        if existing:
            prepared["unique_code"] = existing.unique_code
            prepared.setdefault("company_id", existing.company_id)
            prepared.setdefault("area_id", existing.area_id)
        if not prepared.get("unique_code"):
            prepared["unique_code"] = generated_code("CAM")

        prepared["brand"] = prepared.get("brand") or "custom"
        prepared["protocol"] = prepared.get("protocol") or "rtsp"
        prepared["inference_type"] = prepared.get("inference_type") or "inactiva"
        if prepared["inference_type"] not in self.inference_types:
            raise DeviceAdminError("Tipo de inferencia invalido")

        if prepared.get("rbox_id") or prepared.get("rbox"):
            prepared["uses_rbox"] = True

        if raw_password:
            prepared["password_encrypted"] = self.cipher.encrypt(raw_password)
        elif existing:
            prepared.pop("password_encrypted", None)

        if normalize_brand(prepared.get("brand")) in {"dahua", "hikvision"}:
            prepared["port"] = prepared.get("port") or 554
            prepared["channel"] = prepared.get("channel") or 1
            prepared["quality"] = prepared.get("quality") or ("substream" if prepared.get("stream") == 1 else "mainstream")
            prepared["stream"] = prepared.get("stream") if prepared.get("stream") is not None else (1 if prepared["quality"] == "substream" else 0)
            prepared["rtsp_url"] = self._build_rtsp_url(prepared, raw_password, existing)

        return prepared

    def _build_rtsp_url(self, data: dict, raw_password: str | None, existing: Camera | None) -> str | None:
        ip = (data.get("ip") or "").strip()
        if not ip:
            return data.get("rtsp_url")

        brand = normalize_brand(data.get("brand"))
        user = (data.get("username") or "").strip()
        password = raw_password or (self.cipher.decrypt(existing.password_encrypted) if existing else "") or ""
        port = int(data.get("port") or 554)
        channel = int(data.get("channel") or 1)
        quality = (data.get("quality") or "mainstream").strip().lower()
        subtype = data.get("stream")
        subtype = int(subtype) if subtype is not None else (1 if quality == "substream" else 0)
        auth = f"{quote(user)}:{quote(password)}@" if user or password else ""

        if brand == "hikvision":
            suffix = "02" if quality == "substream" or subtype == 1 else "01"
            hikvision_channel = channel if channel >= 100 else int(f"{channel}{suffix}")
            return f"rtsp://{auth}{ip}:{port}/Streaming/Channels/{hikvision_channel}"

        return f"rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={channel}&subtype={1 if quality == 'substream' or subtype == 1 else 0}"


class RBoxAdminService:
    @transaction.atomic
    def create(self, data: dict) -> RBox:
        prepared = dict(data)
        prepared["serial"] = prepared.get("serial") or generated_code("RBOX")
        rbox = RBox(**prepared)
        rbox.save()
        return rbox

    @transaction.atomic
    def update(self, rbox: RBox, data: dict) -> RBox:
        prepared = dict(data)
        if not prepared.get("serial"):
            prepared.pop("serial", None)
        for field, value in prepared.items():
            setattr(rbox, field, value)
        rbox.save()
        return rbox

    @transaction.atomic
    def delete(self, rbox: RBox) -> None:
        rbox.active = False
        rbox.deleted_at = timezone.now()
        rbox.save(update_fields=["active", "deleted_at"])


class VehicleAdminService:
    plate_pattern = re.compile(r"^([A-Z]{3})(\d{1,4})$")

    @transaction.atomic
    def create(self, data: dict) -> Vehicle:
        prepared = self._prepare(data)
        self._validate_unique(prepared)
        vehicle = Vehicle(**prepared)
        vehicle.save()
        return vehicle

    @transaction.atomic
    def update(self, vehicle: Vehicle, data: dict) -> Vehicle:
        prepared = self._prepare(data, existing=vehicle)
        self._validate_unique(prepared, existing=vehicle)
        for field, value in prepared.items():
            setattr(vehicle, field, value)
        vehicle.save()
        return vehicle

    @transaction.atomic
    def delete(self, vehicle: Vehicle) -> None:
        vehicle.active = False
        vehicle.deleted_at = timezone.now()
        vehicle.save(update_fields=["active", "deleted_at"])

    def _prepare(self, data: dict, *, existing: Vehicle | None = None) -> dict:
        prepared = dict(data)
        if existing:
            prepared["unique_code"] = existing.unique_code
            prepared.setdefault("company_id", existing.company_id)
            prepared.setdefault("area_id", existing.area_id)
        prepared["vehicle_type"] = prepared.get("vehicle_type") or "auto"
        prepared["name"] = (prepared.get("name") or prepared.get("plate") or "Vehiculo").strip()
        if prepared.get("plate"):
            prepared["plate"] = self._normalize_plate(prepared.get("plate"))
        if not prepared.get("unique_code"):
            prepared["unique_code"] = prepared.get("plate") or generated_code("CAR")
        return prepared

    def _validate_unique(self, data: dict, *, existing: Vehicle | None = None) -> None:
        company_id = data.get("company_id") or getattr(data.get("company"), "id", None)
        if not company_id:
            raise DeviceAdminError("Empresa requerida")

        plate = self._normalize_plate(data.get("plate"))
        unique_code = str(data.get("unique_code") or "").strip()
        queryset = Vehicle.all_objects.filter(company_id=company_id, deleted_at__isnull=True)
        if existing:
            queryset = queryset.exclude(id=existing.id)

        if plate and queryset.filter(plate__iexact=plate).exists():
            raise DeviceAdminError("Ya existe un vehiculo con esa placa en la empresa")
        if unique_code and queryset.filter(unique_code__iexact=unique_code).exists():
            raise DeviceAdminError("Ya existe un vehiculo con ese codigo GPS en la empresa")

    @staticmethod
    def _normalize_plate(value: object) -> str:
        cleaned = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
        if not cleaned:
            return ""
        match = VehicleAdminService.plate_pattern.fullmatch(cleaned)
        if not match:
            raise DeviceAdminError("La placa debe tener 3 letras y hasta 4 numeros, ejemplo ABC9140")
        letters, digits = match.groups()
        return f"{letters}{digits.zfill(4)}"


class DroneAdminService:
    def __init__(self, streams: StreamProvisioningService | None = None):
        self.streams = streams or StreamProvisioningService()

    @transaction.atomic
    def create(self, data: dict) -> Drone:
        prepared = self._prepare(data)
        self._validate_unique(prepared)
        drone = Drone(**prepared)
        drone.save()
        if drone.can_publish:
            self.streams.ensure_drone_stream(drone)
        return drone

    @transaction.atomic
    def update(self, drone: Drone, data: dict) -> Drone:
        prepared = self._prepare(data, existing=drone)
        self._validate_unique(prepared, existing=drone)
        for field, value in prepared.items():
            setattr(drone, field, value)
        drone.save()
        if drone.active and drone.can_publish:
            self.streams.ensure_drone_stream(drone)
        else:
            self.streams.disable_drone_stream(drone)
        return drone

    @transaction.atomic
    def delete(self, drone: Drone) -> None:
        drone.active = False
        drone.deleted_at = timezone.now()
        drone.save(update_fields=["active", "deleted_at"])
        self.streams.disable_drone_stream(drone)

    def _prepare(self, data: dict, *, existing: Drone | None = None) -> dict:
        prepared = dict(data)
        if existing:
            prepared["unique_code"] = existing.unique_code
            prepared.setdefault("company_id", existing.company_id)
            prepared.setdefault("area_id", existing.area_id)
        provider = str(prepared.get("provider") or "robiotec").strip().lower()
        prepared["provider"] = provider
        prepared["drone_type"] = str(prepared.get("drone_type") or provider or "robiotec").strip().lower()
        prepared["name"] = str(prepared.get("name") or prepared.get("serial_number") or "Dron").strip()
        if not prepared.get("manufacturer"):
            prepared["manufacturer"] = "DJI" if provider == "dji" else "Robiotec"
        if not prepared.get("unique_code"):
            prefix = "DJI" if provider == "dji" else "DRN"
            prepared["unique_code"] = generated_code(prefix)
        prepared["status"] = prepared.get("status") or "activo"
        return prepared

    def _validate_unique(self, data: dict, *, existing: Drone | None = None) -> None:
        company_id = data.get("company_id") or getattr(data.get("company"), "id", None)
        if not company_id:
            raise DeviceAdminError("Empresa requerida")
        unique_code = str(data.get("unique_code") or "").strip()
        if not unique_code:
            raise DeviceAdminError("Codigo unico requerido")
        queryset = Drone.all_objects.filter(company_id=company_id, deleted_at__isnull=True, unique_code__iexact=unique_code)
        if existing:
            queryset = queryset.exclude(id=existing.id)
        if queryset.exists():
            raise DeviceAdminError("Ya existe un dron con ese codigo en la empresa")
