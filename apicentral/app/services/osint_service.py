from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.geojson_helpers import bbox_intersects, number, rounded_geometry


class OsintDataError(RuntimeError):
    pass


class OsintService:
    LAYER_ALIASES = {
        "all": "",
        "eventos": "category:event",
        "gdo_point": "category:gdo_point",
        "upc_point": "category:upc_point",
        "gdo_zone": "category:gdo_zone",
        "policias": "source:punto_interes_policias",
        "gdos": "source:punto_interes_gdos.puntos",
        "zonas_gdo": "source:zonas_poligonos_gdo",
        "rutas_narcotrafico": "source:rutas_narcotrafico",
    }

    def __init__(self, geojson_path: str, report_path: str) -> None:
        self.geojson_path = Path(geojson_path).expanduser()
        self.report_path = Path(report_path).expanduser()
        self._cache: dict[str, Any] = {"mtime": None, "features": []}

    def features(self) -> list[dict[str, Any]]:
        if not self.geojson_path.exists():
            raise OsintDataError(f"No existe {self.geojson_path}")
        mtime = self.geojson_path.stat().st_mtime
        if self._cache["mtime"] != mtime:
            try:
                payload = json.loads(self.geojson_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise OsintDataError(f"GeoJSON OSINT invalido: {exc}") from exc
            features = payload.get("features") if isinstance(payload, dict) else []
            self._cache["features"] = features if isinstance(features, list) else []
            self._cache["mtime"] = mtime
        return self._cache["features"]

    def report(self) -> dict[str, Any]:
        if not self.report_path.exists():
            return {"available": False, "report_file": str(self.report_path)}
        try:
            payload = json.loads(self.report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OsintDataError(f"Reporte OSINT invalido: {exc}") from exc
        return {"available": True, **payload}

    def layer_matches(self, feature: dict[str, Any], layer: str) -> bool:
        normalized = str(layer or "").strip()
        if not normalized or normalized == "all":
            return True
        normalized = self.LAYER_ALIASES.get(normalized, normalized)
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            return False
        if normalized.startswith("category:"):
            return str(properties.get("category") or "") == normalized.split(":", 1)[1]
        if normalized.startswith("source:"):
            return str(properties.get("source") or "") == normalized.split(":", 1)[1]
        return (
            str(properties.get("source") or "") == normalized
            or str(properties.get("category") or "") == normalized
        )

    def public_feature(self, feature: dict[str, Any]) -> dict[str, Any]:
        properties = feature.get("properties") if isinstance(feature, dict) else {}
        properties = properties if isinstance(properties, dict) else {}
        public_properties = {
            key: value
            for key, value in properties.items()
            if key
            in {
                "source",
                "category",
                "geometry_kind",
                "id",
                "nombre",
                "titulo",
                "tipo",
                "tipo_id",
                "codigo_alfanumerico",
                "fecha_infraccion",
                "descripcion",
                "agrupacion",
                "url_icono",
                "url_noticia",
                "color",
                "parametro_id",
            }
        }
        return {
            "type": "Feature",
            "id": feature.get("id"),
            "properties": public_properties,
            "geometry": rounded_geometry(feature.get("geometry")),
        }

    def layers(self, bbox: str, limit: int = 2000, layer: str = "") -> dict[str, Any]:
        parts = [number(part) for part in bbox.split(",")]
        if len(parts) != 4 or any(part is None for part in parts):
            raise ValueError("bbox invalido. Usa west,south,east,north.")
        west, south, east, north = (float(part) for part in parts if part is not None)
        if west > east or south > north:
            raise ValueError("bbox invalido. Revisa el orden west,south,east,north.")

        safe_limit = max(1, min(int(limit or 2000), 10000))
        selected = [
            self.public_feature(feature)
            for feature in self.features()
            if (
                isinstance(feature, dict)
                and self.layer_matches(feature, layer)
                and bbox_intersects(feature, west, south, east, north)
            )
        ][:safe_limit]
        return {"type": "FeatureCollection", "features": selected, "count": len(selected), "layer": layer or "all"}
