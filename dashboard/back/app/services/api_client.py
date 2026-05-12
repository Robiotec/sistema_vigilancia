from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from back.app.config import Settings


class BaseApiClient:
    """Cliente padre para llamadas JSON a servicios HTTP."""

    def __init__(self, base_url: str, timeout: int = 20) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def request(self, path: str, *, method: str = "GET", token: str | None = None, data: Any = None) -> Any:
        url = urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))
        body = None if data is None else json.dumps(data).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = UrlRequest(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
            except json.JSONDecodeError:
                payload = {"detail": detail or exc.reason}
            raise RuntimeError(payload.get("detail") or payload.get("error") or exc.reason) from exc
        except URLError as exc:
            raise RuntimeError("API central no disponible") from exc


class DashboardApiClient(BaseApiClient):
    """Cliente hijo especializado para el Dashboard Robiotec."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings.api_base_url)
