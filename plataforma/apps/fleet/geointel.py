from __future__ import annotations

import requests
from django.conf import settings


class GeoIntelError(RuntimeError):
    pass


class GeoIntelService:
    """Proxy de solo lectura hacia apicentral para las capas ARCOM y OSINT.

    apicentral ya sirve estos datos filtrados por bbox desde los GeoJSON
    locales (concesiones mineras / puntos OSINT); Django solo agrega el
    gate de autenticacion y reenvia, en vez de duplicar el filtrado
    geoespacial.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 6.0):
        self.base_url = (base_url or getattr(settings, "ROBIOTEC_APICENTRAL_URL", "") or "http://127.0.0.1:8003").rstrip("/")
        self.timeout = timeout

    def arcom_concessions(self, bbox: str, limit: int = 120) -> dict[str, object]:
        return self._get("/arcom/concessions", {"bbox": bbox, "limit": limit})

    def arcom_concession_lookup(self, lat: float, lon: float) -> dict[str, object]:
        return self._get("/arcom/concession-lookup", {"lat": lat, "lon": lon})

    def osint_layers(self, bbox: str, limit: int = 2000, layer: str = "") -> dict[str, object]:
        return self._get("/osint/layers", {"bbox": bbox, "limit": limit, "layer": layer})

    def _get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        try:
            response = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GeoIntelError(str(exc)) from exc
        return response.json()
