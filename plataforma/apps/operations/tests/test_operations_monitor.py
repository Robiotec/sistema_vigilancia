from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.services import ServiceResult
from apps.operations.services import EndpointProbe, OperationsMonitorService, SystemdProbe
from apps.streaming.services import MediaMTXPath


class OperationsMonitorServiceTests(SimpleTestCase):
    def test_overview_marks_noncritical_failed_service_as_warning(self):
        service = OperationsMonitorService(
            systemd_runner=lambda name: {
                "LoadState": "loaded",
                "ActiveState": "failed" if name == "secondary.service" else "active",
                "SubState": "failed" if name == "secondary.service" else "running",
                "Description": name,
            },
            http_getter=lambda url, timeout: (200, 12.5, ""),
            mediamtx=_MediaMTX(ok=True),
        )
        service.systemd_probes = [
            SystemdProbe("critical.service", "Critico", "Core", critical=True),
            SystemdProbe("secondary.service", "Secundario", "Core", critical=False),
        ]

        payload = service.overview()

        self.assertEqual(payload["summary"]["status"], "warning")
        self.assertEqual(payload["summary"]["systemd_ok"], 1)
        self.assertEqual(payload["summary"]["systemd_warning"], 1)
        self.assertEqual(payload["summary"]["systemd_error"], 0)

    def test_overview_marks_critical_endpoint_failure_as_error(self):
        service = OperationsMonitorService(
            systemd_runner=lambda name: {"LoadState": "loaded", "ActiveState": "active", "SubState": "running"},
            http_getter=lambda url, timeout: (503 if "bad" in url else 200, 5.0, "down"),
            mediamtx=_MediaMTX(ok=True),
        )
        service.systemd_probes = [SystemdProbe("critical.service", "Critico", "Core", critical=True)]
        service._endpoint_probes = lambda: [
            EndpointProbe("good", "Good", "http://local/good", "Core", critical=True),
            EndpointProbe("bad", "Bad", "http://local/bad", "Core", critical=True),
        ]

        payload = service.overview()

        self.assertEqual(payload["summary"]["status"], "error")
        self.assertEqual(payload["summary"]["endpoints_ok"], 1)
        self.assertEqual(payload["endpoints"][1]["status"], "error")


class _MediaMTX:
    def __init__(self, *, ok: bool):
        self.ok = ok

    def list_paths(self):
        if not self.ok:
            return ServiceResult.failure("mediamtx down")
        return ServiceResult.success([MediaMTXPath(name="CAM-001", ready=True, source="rtsp")])
