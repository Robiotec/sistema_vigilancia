#!/usr/bin/env python3
"""
Descarga capas publicas OSINT desde vectorinternational.ai y genera:

- osint_raw/*.json: respuestas crudas por endpoint.
- osint_layers.geojson: FeatureCollection normalizado para el mapa.
- osint_descarga_reporte.json: resumen de descarga.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


BASE_URL = os.getenv("OSINT_BASE_URL", "https://vectorinternational.ai/api").rstrip("/")
OUT_DIR = Path(os.getenv("OSINT_OUT_DIR", str(Path(__file__).parent))).expanduser()
RAW_DIR = OUT_DIR / "osint_raw"
OUT_GEOJSON = OUT_DIR / "osint_layers.geojson"
OUT_REPORT = OUT_DIR / "osint_descarga_reporte.json"

TIMEOUT_SEC = max(float(os.getenv("OSINT_REQUEST_TIMEOUT_SEC", "60")), 1.0)
MAX_RETRIES = max(1, int(os.getenv("OSINT_MAX_RETRIES", "4")))
SLEEP_SECONDS = max(float(os.getenv("OSINT_SLEEP_SECONDS", "0.2")), 0.0)

EVENT_LAYER_IDS = [
    "UNIDADES_FFAA",
    "RESIDENCIAS_CRIMINALES",
    "MARCADORES_CRIMINALES",
    "OPERATIVOS_FFOO",
    "HOMICIDO_SICARIATO",
    "PASO_ILEGAL",
    "PASO_OFICIAL",
    "MINERIA_ILEGAL",
]
EXCLUDED_ZONE_NAMES = {"cantones"}
EXCLUDED_ZONE_IDS = {1, "1"}

ENDPOINTS = {
    "punto_interes_gdos": "/punto-interes/gdos",
    "zonas_poligonos_gdo": "/zonas/poligonos-gdo",
    "rutas_narcotrafico": "/rutas-narcotrafico",
    "punto_interes_policias": "/punto-interes/policias",
    "zonas_tipos_zonas": "/zonas/tipos-zonas",
    "parametros": "/parametros",
    "eventos_tipos_eventos": "/eventos/tipos-eventos",
    **{
        f"eventos_{layer_id.lower()}": f"/eventos/eventos-capas-id?id_tipo_evento={layer_id}"
        for layer_id in EVENT_LAYER_IDS
    },
}


def request_json(session: requests.Session, path: str) -> dict[str, Any]:
    url = urljoin(f"{BASE_URL}/", path.lstrip("/"))
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=TIMEOUT_SEC, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = str(exc)
            print(f"  Intento {attempt}/{MAX_RETRIES} falló para {path}: {last_error}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Consulta fallida {path}: {last_error}")


def payload_data(payload: Any) -> Any:
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def point_feature(item: dict[str, Any], source: str, category: str) -> dict[str, Any] | None:
    lat = finite_number(item.get("latitud") or item.get("lat"))
    lon = finite_number(item.get("longitud") or item.get("lng") or item.get("lon"))
    if lat is None or lon is None:
        return None
    return {
        "type": "Feature",
        "id": f"{source}:{item.get('id', '')}",
        "properties": {
            "source": source,
            "category": category,
            "geometry_kind": "point",
            "id": item.get("id"),
            "nombre": item.get("nombre") or item.get("titulo") or item.get("codigo_alfanumerico"),
            "titulo": item.get("titulo"),
            "tipo": item.get("tipo_interes") or (item.get("tipo_evento") or {}).get("nombre"),
            "tipo_id": item.get("tipo_punto_interes_id") or (item.get("tipo_evento") or {}).get("id"),
            "codigo_alfanumerico": item.get("codigo_alfanumerico"),
            "fecha_infraccion": item.get("fecha_infraccion"),
            "descripcion": item.get("circunstancias_hecho") or item.get("pop_up") or "",
            "agrupacion": item.get("agrupacion"),
            "url_icono": item.get("url_icono") or (item.get("tipo_evento") or {}).get("url_icono"),
            "url_noticia": item.get("url_noticia"),
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def polygon_feature(item: dict[str, Any], source: str, category: str) -> dict[str, Any] | None:
    if item.get("id") in EXCLUDED_ZONE_IDS:
        return None
    if str(item.get("nombre") or "").strip().lower() in EXCLUDED_ZONE_NAMES:
        return None
    polygons = item.get("puntos")
    if not isinstance(polygons, list) or not polygons:
        return None
    return {
        "type": "Feature",
        "id": f"{source}:{item.get('id', '')}",
        "properties": {
            "source": source,
            "category": category,
            "geometry_kind": "polygon",
            "id": item.get("id"),
            "nombre": item.get("nombre"),
            "tipo": "Zona GDO" if category == "gdo_zone" else category,
            "descripcion": item.get("descripcion") or "",
            "color": item.get("color"),
            "url_icono": item.get("icon") or item.get("url_icono"),
            "parametro_id": item.get("parametro_id"),
        },
        "geometry": {"type": "MultiPolygon", "coordinates": polygons},
    }


def line_feature(item: dict[str, Any], source: str, category: str) -> dict[str, Any] | None:
    geometry = item.get("puntos")
    if not isinstance(geometry, dict):
        return None
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type not in {"LineString", "MultiLineString"} or not isinstance(coordinates, list):
        return None
    return {
        "type": "Feature",
        "id": f"{source}:{item.get('id', '')}",
        "properties": {
            "source": source,
            "category": category,
            "geometry_kind": "line",
            "id": item.get("id"),
            "nombre": item.get("nombre") or item.get("descripcion") or item.get("tipo_ruta"),
            "titulo": item.get("tipo_ruta"),
            "tipo": item.get("tipo_ruta") or "Ruta",
            "descripcion": item.get("descripcion") or "",
            "color": item.get("color"),
        },
        "geometry": {"type": geometry_type, "coordinates": coordinates},
    }


def normalize(raw_payloads: dict[str, Any]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []

    gdos = payload_data(raw_payloads.get("punto_interes_gdos"))
    if isinstance(gdos, dict):
        for item in gdos.get("puntos") or []:
            if isinstance(item, dict) and (feature := point_feature(item, "punto_interes_gdos.puntos", "gdo_point")):
                features.append(feature)

    for item in payload_data(raw_payloads.get("zonas_poligonos_gdo")) or []:
        if isinstance(item, dict) and (feature := polygon_feature(item, "zonas_poligonos_gdo", "gdo_zone")):
            features.append(feature)

    rutas = payload_data(raw_payloads.get("rutas_narcotrafico"))
    if isinstance(rutas, dict):
        rutas = rutas.get("rutas")
    for item in rutas or []:
        if isinstance(item, dict) and (feature := line_feature(item, "rutas_narcotrafico", "narco_route")):
            features.append(feature)

    for item in payload_data(raw_payloads.get("punto_interes_policias")) or []:
        if isinstance(item, dict) and (feature := point_feature(item, "punto_interes_policias", "upc_point")):
            features.append(feature)

    for layer_id in EVENT_LAYER_IDS:
        source = f"eventos_{layer_id.lower()}"
        for item in payload_data(raw_payloads.get(source)) or []:
            if isinstance(item, dict) and (feature := point_feature(item, source, "event")):
                features.append(feature)

    return features


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    raw_payloads: dict[str, Any] = {}
    for name, path in ENDPOINTS.items():
        print(f"Descargando {name}: {path}")
        payload = request_json(session, path)
        raw_payloads[name] = payload
        (RAW_DIR / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        time.sleep(SLEEP_SECONDS)

    features = normalize(raw_payloads)
    OUT_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "endpoints": ENDPOINTS,
        "feature_count": len(features),
        "geojson_file": str(OUT_GEOJSON),
        "geojson_size_mb": round(OUT_GEOJSON.stat().st_size / 1024 / 1024, 2),
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DESCARGA OSINT TERMINADA")
    print(f"Features normalizadas: {len(features)}")
    print(f"GeoJSON: {OUT_GEOJSON}")


if __name__ == "__main__":
    main()
    