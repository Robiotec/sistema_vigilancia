from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Callable

import requests
from django.conf import settings
from django.utils import timezone

from apps.streaming.services import MediaMTXClient


@dataclass(frozen=True)
class SystemdProbe:
    name: str
    label: str
    category: str
    critical: bool = True


@dataclass(frozen=True)
class EndpointProbe:
    name: str
    label: str
    url: str
    category: str
    critical: bool = True


SystemdRunner = Callable[[str], dict[str, str]]
HttpGetter = Callable[[str, float], tuple[int, float, str]]


class OperationsMonitorService:
    systemd_probes = [
        SystemdProbe("robiotec-django.service", "Dashboard principal", "Plataforma"),
        SystemdProbe("robiotec-apicentral.service", "API central", "Plataforma"),
        SystemdProbe("robiotec-celery.service", "Celery worker", "Tareas"),
        SystemdProbe("robiotec-celerybeat.service", "Celery beat", "Tareas"),
        SystemdProbe("robiotec-mediamtx.service", "MediaMTX", "Streaming"),
        SystemdProbe("nginx.service", "Nginx", "Infraestructura"),
        SystemdProbe("postgresql@16-main.service", "PostgreSQL", "Infraestructura"),
        SystemdProbe("redis-server.service", "Redis", "Infraestructura"),
        SystemdProbe("robiotec-state-camera-sync.service", "Sync estado camaras", "Streaming", critical=False),
        SystemdProbe("robiotec-retention-cleanup.service", "Limpieza de retencion", "Mantenimiento", critical=False),
        SystemdProbe("robiotec-arcom-download.service", "ARCOM downloader", "Datos externos", critical=False),
        SystemdProbe("robiotec-osint-download.service", "OSINT downloader", "Datos externos", critical=False),
    ]

    def __init__(
        self,
        *,
        systemd_runner: SystemdRunner | None = None,
        http_getter: HttpGetter | None = None,
        mediamtx: MediaMTXClient | None = None,
        timeout: float = 3.0,
    ):
        self.systemd_runner = systemd_runner or self._systemd_show
        self.http_getter = http_getter or self._http_get
        self.mediamtx = mediamtx or MediaMTXClient(timeout=timeout)
        self.timeout = timeout

    def overview(self) -> dict[str, object]:
        systemd_items = [self._systemd_item(probe) for probe in self.systemd_probes]
        endpoint_items = [self._endpoint_item(probe) for probe in self._endpoint_probes()]
        mediamtx = self._mediamtx_summary()
        status_values = [item["status"] for item in systemd_items + endpoint_items]
        if not mediamtx["ok"]:
            status_values.append("error")
        elif int(mediamtx["ready_paths"]) == 0:
            status_values.append("warning")
        return {
            "generated_at": timezone.now().isoformat(),
            "summary": {
                "status": self._worst_status(status_values),
                "systemd_total": len(systemd_items),
                "systemd_ok": sum(1 for item in systemd_items if item["status"] == "ok"),
                "systemd_warning": sum(1 for item in systemd_items if item["status"] == "warning"),
                "systemd_error": sum(1 for item in systemd_items if item["status"] == "error"),
                "endpoints_total": len(endpoint_items),
                "endpoints_ok": sum(1 for item in endpoint_items if item["status"] == "ok"),
                "mediamtx_ready_paths": mediamtx["ready_paths"],
                "mediamtx_total_paths": mediamtx["total_paths"],
            },
            "systemd": systemd_items,
            "endpoints": endpoint_items,
            "mediamtx": mediamtx,
        }

    def _endpoint_probes(self) -> list[EndpointProbe]:
        return [
            EndpointProbe(
                "django-health",
                "Django health",
                str(getattr(settings, "ROBIOTEC_DJANGO_HEALTH_URL", "http://127.0.0.1:8020/health/")),
                "Plataforma",
            ),
            EndpointProbe(
                "apicentral-health",
                "API central health",
                str(getattr(settings, "ROBIOTEC_APICENTRAL_HEALTH_URL", "http://127.0.0.1:8003/health")),
                "Plataforma",
            ),
            EndpointProbe(
                "mediamtx-paths",
                "MediaMTX paths",
                f"{str(getattr(settings, 'MEDIAMTX_API_URL', 'http://127.0.0.1:9997')).rstrip('/')}/v3/paths/list",
                "Streaming",
            ),
        ]

    def _systemd_item(self, probe: SystemdProbe) -> dict[str, object]:
        try:
            values = self.systemd_runner(probe.name)
        except Exception as exc:
            values = {"error": str(exc), "ActiveState": "unknown", "SubState": "unknown", "LoadState": "unknown"}
        active_state = values.get("ActiveState", "unknown")
        sub_state = values.get("SubState", "unknown")
        load_state = values.get("LoadState", "unknown")
        result = values.get("Result", "")
        status = self._systemd_status(active_state, sub_state, load_state, probe.critical)
        return {
            "name": probe.name,
            "label": probe.label,
            "category": probe.category,
            "critical": probe.critical,
            "status": status,
            "active_state": active_state,
            "sub_state": sub_state,
            "load_state": load_state,
            "unit_file_state": values.get("UnitFileState", ""),
            "result": result,
            "description": values.get("Description", ""),
            "error": values.get("error", ""),
        }

    def _endpoint_item(self, probe: EndpointProbe) -> dict[str, object]:
        try:
            http_status, latency_ms, error = self.http_getter(probe.url, self.timeout)
        except Exception as exc:
            http_status, latency_ms, error = 0, 0.0, str(exc)
        ok = 200 <= int(http_status) < 400
        status = "ok" if ok else ("error" if probe.critical else "warning")
        return {
            "name": probe.name,
            "label": probe.label,
            "category": probe.category,
            "critical": probe.critical,
            "url": probe.url,
            "status": status,
            "http_status": http_status,
            "latency_ms": round(latency_ms, 1),
            "error": error,
        }

    def _mediamtx_summary(self) -> dict[str, object]:
        result = self.mediamtx.list_paths()
        if not result.ok:
            return {"ok": False, "status": "error", "ready_paths": 0, "total_paths": 0, "error": result.error, "items": []}
        paths = result.value or []
        return {
            "ok": True,
            "status": "ok" if any(path.ready for path in paths) else "warning",
            "ready_paths": sum(1 for path in paths if path.ready),
            "total_paths": len(paths),
            "error": "",
            "items": [
                {"name": path.name, "ready": path.ready, "source": path.source or ""}
                for path in sorted(paths, key=lambda item: item.name)[:80]
            ],
        }

    @staticmethod
    def _systemd_status(active_state: str, sub_state: str, load_state: str, critical: bool) -> str:
        if load_state == "not-found":
            return "error" if critical else "warning"
        if active_state == "active":
            return "ok"
        if active_state == "activating":
            return "warning"
        if active_state == "failed" and not critical:
            return "warning"
        if active_state == "inactive" and not critical:
            return "warning"
        if sub_state in {"exited", "dead"} and not critical:
            return "warning"
        return "error"

    @staticmethod
    def _worst_status(status_values: list[object]) -> str:
        statuses = {str(value) for value in status_values}
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        return "ok"

    @staticmethod
    def _systemd_show(service_name: str) -> dict[str, str]:
        command = [
            "systemctl",
            "show",
            service_name,
            "--no-pager",
            "--property=LoadState,ActiveState,SubState,Description,UnitFileState,Result",
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=2.5)
        values = {}
        for line in completed.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        if completed.returncode not in {0, 3} and not values:
            values["error"] = completed.stderr.strip() or f"systemctl exit {completed.returncode}"
        return values

    @staticmethod
    def _http_get(url: str, timeout: float) -> tuple[int, float, str]:
        started = time.monotonic()
        try:
            response = requests.get(url, timeout=timeout)
        except requests.RequestException as exc:
            return 0, (time.monotonic() - started) * 1000, str(exc)
        elapsed_ms = (time.monotonic() - started) * 1000
        error = "" if response.ok else response.text[:180]
        return response.status_code, elapsed_ms, error
