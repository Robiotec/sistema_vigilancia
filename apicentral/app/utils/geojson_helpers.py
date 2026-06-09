"""Utilidades GeoJSON compartidas entre ArcomService y OsintService."""
from __future__ import annotations

from typing import Any


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


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
    feature: dict[str, Any], west: float, south: float, east: float, north: float
) -> bool:
    bbox = feature_bbox(feature)
    if not bbox:
        return False
    min_x, min_y, max_x, max_y = bbox
    return min_x <= east and max_x >= west and min_y <= north and max_y >= south
