from __future__ import annotations

import json
import re
import ssl
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from back.app.config import Settings


def normalize_plate(value: Any) -> str:
    raw = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum())
    match = re.fullmatch(r"([A-Z]{2,3})(\d{3,4})", raw)
    if not match:
        return raw
    prefix, number = match.groups()
    return f"{prefix}{number.zfill(4)}"


class PlateLookupClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def lookup(self, plate: str) -> dict[str, Any] | None:
        normalized = normalize_plate(plate)
        if len(normalized) < 5 or not self.settings.plate_lookup_api_url:
            return None

        now = time.time()
        with self._lock:
            cached = self._cache.get(normalized)
            if cached and now - cached[0] < self.settings.plate_lookup_cache_ttl_seconds:
                return dict(cached[1])

        url = f"{self.settings.plate_lookup_api_url.rstrip('/')}/{quote(normalized)}/"
        headers = {"Accept": "application/json"}
        if self.settings.plate_lookup_api_token:
            headers["X-Plate-Lookup-Token"] = self.settings.plate_lookup_api_token

        try:
            request = Request(url, headers=headers)
            context = ssl._create_unverified_context() if url.startswith("https://") else None
            with urlopen(
                request,
                timeout=float(self.settings.plate_lookup_timeout_seconds),
                context=context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

        record = payload.get("record") if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            return None

        with self._lock:
            self._cache[normalized] = (now, dict(record))
        return dict(record)

