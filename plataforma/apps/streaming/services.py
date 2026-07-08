from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import quote

import requests
from django.conf import settings
from django.db.models import Q

from apps.accounts.roles import LegacyRoleService
from apps.alerts.models import CameraEventHistory
from apps.alerts.services import EventHistoryService
from apps.core.services import ServiceResult
from apps.devices.models import Camera
from apps.streaming.models import StreamConfig, StreamPath


@dataclass(frozen=True)
class MediaMTXPath:
    name: str
    ready: bool
    source: str | None = None


class MediaMTXClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or settings.MEDIAMTX_API_URL).rstrip("/")
        self.timeout = timeout

    def list_paths(self) -> ServiceResult[list[MediaMTXPath]]:
        try:
            response = requests.get(f"{self.base_url}/v3/paths/list", timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            return ServiceResult.failure(str(exc))

        items = response.json().get("items", [])
        paths = [
            MediaMTXPath(
                name=item.get("name", ""),
                ready=bool(item.get("ready")),
                source=item.get("source", {}).get("type") if isinstance(item.get("source"), dict) else None,
            )
            for item in items
            if item.get("name")
        ]
        return ServiceResult.success(paths)


class StreamUrlBuilder:
    @staticmethod
    def viewer_url(path: str) -> str:
        normalized_path = quote(path.strip("/"), safe="/")
        base = str(getattr(settings, "MEDIAMTX_WEBRTC_BASE_URL", "/mediamtx") or "/mediamtx").rstrip("/")
        if base.startswith(("http://", "https://")):
            return f"{base}/{normalized_path}/"
        public_host = str(getattr(settings, "ROBIOTEC_PUBLIC_HOST", "") or "").strip()
        if public_host and public_host not in {"127.0.0.1", "localhost"}:
            return f"https://{public_host}{base}/{normalized_path}/"
        return f"{base}/{normalized_path}/"

    @classmethod
    def whep_url(cls, path: str) -> str:
        return f"{cls.viewer_url(path).rstrip('/')}/whep"


class CameraViewerService:
    inference_types = {"rostro", "placa", "zona", "movimiento", "inactiva"}

    def __init__(self, mediamtx: MediaMTXClient | None = None, roles: LegacyRoleService | None = None):
        self.mediamtx = mediamtx or MediaMTXClient()
        self.roles = roles or LegacyRoleService()

    def catalog(self, current_user=None, *, event_limit: int = 6) -> dict[str, object]:
        path_result = self.mediamtx.list_paths()
        paths = {item.name: item for item in path_result.value} if path_result.ok and path_result.value else {}
        stream_by_camera = self._stream_configs_by_camera()
        stream_paths_by_camera = self._stream_paths_by_camera()
        cameras = []
        for camera in self._camera_queryset(current_user).order_by("name"):
            stream = stream_by_camera.get(camera.id)
            configured_path = self._camera_path(camera, stream, stream_paths_by_camera.get(camera.id))
            normal_path = self._normal_stream_path(configured_path)
            inference_path = self._inference_stream_path(configured_path)
            mediamtx_path = paths.get(configured_path)
            normal_mediamtx_path = paths.get(normal_path)
            inference_mediamtx_path = paths.get(inference_path)
            configured_online = bool(mediamtx_path and mediamtx_path.ready)
            normal_online = bool(normal_mediamtx_path and normal_mediamtx_path.ready)
            inference_online = bool(inference_mediamtx_path and inference_mediamtx_path.ready)
            online = normal_online or inference_online or configured_online
            cameras.append(
                {
                    "id": str(camera.id),
                    "name": camera.name,
                    "company_id": str(camera.company_id),
                    "company_name": camera.company.name if camera.company_id and camera.company else "",
                    "unique_code": camera.unique_code or "",
                    "camera_type": camera.camera_type,
                    "inference_type": camera.inference_type or "inactiva",
                    "status": camera.status,
                    "active": camera.active,
                    "can_publish": camera.can_publish,
                    "uses_rbox": camera.uses_rbox,
                    "rbox_name": camera.rbox.name if camera.rbox_id and camera.rbox else "",
                    "vehicle_name": camera.vehicle.name if camera.vehicle_id and camera.vehicle else "",
                    "path": configured_path,
                    "viewer_url": self._viewer_url(configured_path) if configured_path else "",
                    "whep_url": StreamUrlBuilder.whep_url(configured_path) if configured_path else "",
                    "normal_path": normal_path,
                    "normal_viewer_url": self._viewer_url(normal_path) if normal_path else "",
                    "normal_whep_url": StreamUrlBuilder.whep_url(normal_path) if normal_path else "",
                    "normal_online": normal_online,
                    "inference_path": inference_path,
                    "inference_viewer_url": self._viewer_url(inference_path) if inference_path else "",
                    "inference_whep_url": StreamUrlBuilder.whep_url(inference_path) if inference_path else "",
                    "inference_online": inference_online,
                    "online": online,
                    "source": mediamtx_path.source if mediamtx_path else "",
                    "stream_status": stream.stream_status if stream else ("en_linea" if online else "sin_stream"),
                    "events": self._recent_events(camera, configured_path, event_limit),
                }
            )
        return {
            "items": cameras,
            "total": len(cameras),
            "mediamtx": {
                "ok": path_result.ok,
                "error": "" if path_result.ok else path_result.error,
                "online_paths": sum(1 for item in paths.values() if item.ready),
            },
        }

    def snapshot(self, camera_id: str, current_user=None, *, mode: str = "default") -> bytes | None:
        camera = self._camera_queryset(current_user).filter(id=camera_id).first()
        if camera is None:
            raise FileNotFoundError("Camara no encontrada")
        stream = self._stream_configs_by_camera([camera.id]).get(camera.id)
        stream_path = self._stream_paths_by_camera([camera.id]).get(camera.id)
        path = self._stream_path_for_mode(self._camera_path(camera, stream, stream_path), mode)
        if not path:
            return None
        # MediaMTX ya recibe el feed (via SRT/RBox) y lo re-sirve por RTSP local;
        # el rtsp_url original de la camara suele estar en una LAN privada del RBox
        # y no es alcanzable desde este servidor.
        mediamtx_rtsp_url = f"rtsp://127.0.0.1:8554/{path}"
        return self._ffmpeg_jpeg(mediamtx_rtsp_url)

    @staticmethod
    def _ffmpeg_jpeg(rtsp_url: str) -> bytes | None:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            tmp_path = handle.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-fflags", "nobuffer", "-flags", "low_delay",
                    "-analyzeduration", "500000", "-probesize", "500000",
                    "-rtsp_transport", "tcp", "-i", rtsp_url,
                    "-vframes", "1", "-vf", "scale=640:360", "-q:v", "5",
                    "-update", "1", "-f", "image2", tmp_path,
                ],
                capture_output=True, timeout=5,
            )
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                with open(tmp_path, "rb") as fh:
                    return fh.read()
        except Exception:
            pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return None

    def camera_events(self, camera_id: str, current_user=None, *, limit: int = 8) -> dict[str, object]:
        camera = self._camera_queryset(current_user).filter(id=camera_id).first()
        if camera is None:
            raise FileNotFoundError("Camara no encontrada")
        stream = self._stream_configs_by_camera([camera.id]).get(camera.id)
        stream_path = self._stream_paths_by_camera([camera.id]).get(camera.id)
        path = self._camera_path(camera, stream, stream_path)
        events = self._recent_events(camera, path, limit)
        return {"items": events, "total": len(events)}

    def set_inference_type(self, camera_id: str, inference_type: str, current_user=None) -> dict[str, object]:
        camera = self._camera_queryset(current_user).filter(id=camera_id).first()
        if camera is None:
            raise FileNotFoundError("Camara no encontrada")
        normalized = (inference_type or "inactiva").strip().lower()
        if normalized not in self.inference_types:
            raise ValueError("Tipo de inferencia invalido")
        camera.inference_type = normalized
        camera.save(update_fields=["inference_type", "updated_at"])
        return {
            "id": str(camera.id),
            "name": camera.name,
            "inference_type": camera.inference_type,
        }

    def _camera_queryset(self, current_user=None):
        queryset = Camera.objects.select_related("company", "area", "rbox", "vehicle").filter(active=True)
        if current_user is None:
            return queryset
        legacy_user = self.roles.legacy_user_for_django_user(current_user)
        if legacy_user is None or self.roles.is_master(current_user):
            return queryset
        return queryset.filter(company_id=legacy_user.company_id)

    @staticmethod
    def _stream_configs_by_camera(camera_ids: list | None = None) -> dict[object, StreamConfig]:
        queryset = StreamConfig.objects.filter(active=True, camera_id__isnull=False).order_by("-updated_at", "mediamtx_path")
        if camera_ids is not None:
            queryset = queryset.filter(camera_id__in=camera_ids)
        result = {}
        for stream in queryset:
            result.setdefault(stream.camera_id, stream)
        return result

    @staticmethod
    def _stream_paths_by_camera(camera_ids: list | None = None) -> dict[object, StreamPath]:
        queryset = StreamPath.objects.filter(active=True, resource_type="camera").order_by("path")
        if camera_ids is not None:
            queryset = queryset.filter(resource_id__in=camera_ids)
        result = {}
        for stream_path in queryset:
            result.setdefault(stream_path.resource_id, stream_path)
        return result

    @staticmethod
    def _camera_path(camera: Camera, stream: StreamConfig | None, stream_path: StreamPath | None) -> str:
        return str(
            (stream.mediamtx_path if stream else "")
            or (stream.publish_path if stream else "")
            or (stream_path.path if stream_path else "")
            or camera.unique_code
            or camera.name
            or ""
        ).strip().strip("/")

    @classmethod
    def _stream_path_for_mode(cls, configured_path: str, mode: str) -> str:
        normalized_mode = str(mode or "default").strip().lower()
        if normalized_mode == "normal":
            return cls._normal_stream_path(configured_path)
        if normalized_mode == "inference":
            return cls._inference_stream_path(configured_path)
        return str(configured_path or "").strip().strip("/")

    @staticmethod
    def _normal_stream_path(path: str) -> str:
        normalized = str(path or "").strip().strip("/")
        return re.sub(r"/+INFERENCE/?$", "", normalized, flags=re.IGNORECASE).strip("/")

    @classmethod
    def _inference_stream_path(cls, path: str) -> str:
        normal_path = cls._normal_stream_path(path)
        return f"{normal_path}/INFERENCE" if normal_path else ""

    @staticmethod
    def _viewer_url(path: str) -> str:
        return StreamUrlBuilder.viewer_url(path)

    @staticmethod
    def _recent_events(camera: Camera, path: str, limit: int) -> list[dict[str, object]]:
        identifiers = {
            path,
            CameraViewerService._normal_stream_path(path),
            CameraViewerService._inference_stream_path(path),
            camera.unique_code or "",
            camera.name or "",
        }
        identifiers = {item for item in identifiers if item}
        queryset = CameraEventHistory.objects.filter(
            Q(camera_id__in=identifiers) | Q(camera_name__in=identifiers)
        ).order_by("-detected_at", "-created_at")[: max(1, min(limit, 20))]
        serializer = EventHistoryService()
        return [serializer.serialize(event) for event in queryset]
