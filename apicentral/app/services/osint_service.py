from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

    @staticmethod
    def rounded_geometry(geometry: Any, precision: int = 5) -> Any:
        if not isinstance(geometry, dict):
            return geometry

        def round_node(node: Any) -> Any:
            if (
                isinstance(node, list)
                and len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
            ):
                rounded = [round(float(node[0]), precision), round(float(node[1]), precision)]
                if len(node) > 2:
                    rounded.extend(node[2:])
                return rounded
            if isinstance(node, list):
                return [round_node(item) for item in node]
            return node

        return {**geometry, "coordinates": round_node(geometry.get("coordinates"))}

    @staticmethod
    def number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    @staticmethod
    def feature_bbox(feature: dict[str, Any]) -> tuple[float, float, float, float] | None:
        cached = feature.get("_robiotec_bbox") if isinstance(feature, dict) else None
        if isinstance(cached, tuple) and len(cached) == 4:
            return cached
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
        values: list[tuple[float, float]] = []

        def collect(node: Any) -> None:
            if (
                isinstance(node, list)
                and len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
            ):
                values.append((float(node[0]), float(node[1])))
                return
            if isinstance(node, list):
                for item in node:
                    collect(item)

        collect(coords)
        if not values:
            return None
        xs = [point[0] for point in values]
        ys = [point[1] for point in values]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        feature["_robiotec_bbox"] = bbox
        return bbox

    def bbox_intersects(
        self, feature: dict[str, Any], west: float, south: float, east: float, north: float
    ) -> bool:
        bbox = self.feature_bbox(feature)
        if not bbox:
            return False
        min_x, min_y, max_x, max_y = bbox
        return min_x <= east and max_x >= west and min_y <= north and max_y >= south

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
        return str(properties.get("source") or "") == normalized or str(properties.get("category") or "") == normalized

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
            "geometry": self.rounded_geometry(feature.get("geometry")),
        }

    def layers(self, bbox: str, limit: int = 2000, layer: str = "") -> dict[str, Any]:
        parts = [self.number(part) for part in bbox.split(",")]
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
                and self.bbox_intersects(feature, west, south, east, north)
            )
        ][:safe_limit]
        return {"type": "FeatureCollection", "features": selected, "count": len(selected), "layer": layer or "all"}
