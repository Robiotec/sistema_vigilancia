from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.geojson_helpers import bbox_intersects, feature_bbox, number, rounded_geometry


class ArcomDataError(RuntimeError):
    pass


class ArcomService:
    def __init__(self, geojson_path: str) -> None:
        self.geojson_path = Path(geojson_path).expanduser()
        self._cache: dict[str, Any] = {"mtime": None, "features": []}

    def features(self) -> list[dict[str, Any]]:
        if not self.geojson_path.exists():
            raise ArcomDataError(f"No existe {self.geojson_path}")
        mtime = self.geojson_path.stat().st_mtime
        if self._cache["mtime"] != mtime:
            try:
                payload = json.loads(self.geojson_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ArcomDataError(f"GeoJSON ARCOM invalido: {exc}") from exc
            features = payload.get("features") if isinstance(payload, dict) else []
            self._cache["features"] = features if isinstance(features, list) else []
            self._cache["mtime"] = mtime
        return self._cache["features"]

    @staticmethod
    def point_in_ring(lon: float, lat: float, ring: list[Any]) -> bool:
        inside = False
        if len(ring) < 3:
            return False
        previous = ring[-1]
        for current in ring:
            if not (
                isinstance(current, list)
                and len(current) >= 2
                and isinstance(previous, list)
                and len(previous) >= 2
            ):
                previous = current
                continue
            x1, y1 = float(current[0]), float(current[1])
            x2, y2 = float(previous[0]), float(previous[1])
            if (y1 > lat) != (y2 > lat):
                x_intersection = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
                if lon < x_intersection:
                    inside = not inside
            previous = current
        return inside

    def point_in_polygon(self, lon: float, lat: float, rings: list[Any]) -> bool:
        if not rings or not self.point_in_ring(lon, lat, rings[0]):
            return False
        return not any(self.point_in_ring(lon, lat, hole) for hole in rings[1:])

    def contains_point(self, feature: dict[str, Any], lat: float, lon: float) -> bool:
        if not bbox_intersects(feature, lon, lat, lon, lat):
            return False
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            return False
        coordinates = geometry.get("coordinates")
        geometry_type = geometry.get("type")
        if geometry_type == "Polygon" and isinstance(coordinates, list):
            return self.point_in_polygon(lon, lat, coordinates)
        if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
            return any(self.point_in_polygon(lon, lat, polygon) for polygon in coordinates)
        return False

    @staticmethod
    def property(properties: dict[str, Any], *names: str) -> str:
        lowered = {str(key).lower(): value for key, value in properties.items()}
        for name in names:
            value = lowered.get(name.lower())
            if value not in (None, ""):
                return str(value)
        for name in names:
            needle = name.lower()
            for key, value in lowered.items():
                if needle in key and value not in (None, ""):
                    return str(value)
        return ""

    def public_properties(self, feature: dict[str, Any]) -> dict[str, Any]:
        properties = feature.get("properties") if isinstance(feature, dict) else {}
        properties = properties if isinstance(properties, dict) else {}
        return {
            "fid": feature.get("id") or properties.get("fid") or properties.get("objectid"),
            "nombre_concesion": self.property(
                properties, "nombre_concesion", "concesion", "nombre", "denominaci", "com"
            ),
            "codigo_catastral": self.property(
                properties, "codigo_catastral", "codigo", "codigo_cat", "cod_catastral", "nam"
            ),
            "estado_actual": self.property(properties, "estado_actual", "estado", "eac"),
            "empresa": self.property(properties, "empresa", "titular", "beneficiario", "ttm"),
            "fase_recurso_mineral": self.property(
                properties, "fase_recurso_mineral", "fase", "recurso", "frm"
            ),
            "tipo_mineral": self.property(properties, "tipo_mineral", "mineral", "tipo"),
        }

    def public_feature(self, feature: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "Feature",
            "id": feature.get("id"),
            "properties": self.public_properties(feature),
            "geometry": rounded_geometry(feature.get("geometry")),
        }

    def concessions(self, bbox: str, limit: int = 120) -> dict[str, Any]:
        parts = [number(part) for part in bbox.split(",")]
        if len(parts) != 4 or any(part is None for part in parts):
            raise ValueError("bbox invalido. Usa west,south,east,north.")
        west, south, east, north = (float(part) for part in parts if part is not None)
        if west > east or south > north:
            raise ValueError("bbox invalido. Revisa el orden west,south,east,north.")

        safe_limit = max(1, min(int(limit or 120), 500))
        selected = [
            self.public_feature(feature)
            for feature in self.features()
            if isinstance(feature, dict) and bbox_intersects(feature, west, south, east, north)
        ][:safe_limit]
        return {"type": "FeatureCollection", "features": selected, "count": len(selected)}

    def concession_lookup(self, lat: float, lon: float) -> dict[str, Any]:
        for feature in self.features():
            if isinstance(feature, dict) and self.contains_point(feature, lat, lon):
                return {"found": True, "concession": self.public_properties(feature)}
        return {"found": False, "concession": None}
