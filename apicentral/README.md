# API central

API FastAPI para autenticacion, permisos, MediaMTX, telemetria y administracion.

## Comandos uv

```bash
uv init --app --name apicentral
uv add fastapi uvicorn sqlalchemy psycopg[binary] pydantic-settings python-jose[cryptography] passlib[bcrypt] httpx python-multipart
uv sync
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8003
```

## Endpoints implementados

- `POST /auth/login`
- `GET /auth/me`
- `POST /stream/token/{path}`
- `GET /streams/{path}/status`
- `POST /mediamtx/auth`
- `POST /telemetry/drone`
- `POST /telemetry/vehicle`
- `GET /arcom/concessions?bbox=west,south,east,north&limit=120`
- `GET /arcom/concession-lookup?lat=-3.015&lon=-78.48`
- `GET /osint/layers?bbox=west,south,east,north&limit=2000&layer=all`
- `GET /osint/report`
- CRUD base para empresas, usuarios, areas, camaras, R-Box, vehiculos, drones y stream paths.

## ARCOM

API Central es la dueña de la lógica de consulta ARCOM. El router esta en:

```text
app/api/routes/arcom.py
```

La lógica de lectura, cache por fecha de modificación, filtro por `bbox` y
consulta punto-en-poligono esta en:

```text
app/services/arcom_service.py
```

La API lee este archivo por defecto:

```text
/root/robiotec/arcom/arcom_catastro.geojson
```

Se puede cambiar con la variable:

```text
ARCOM_GEOJSON=/ruta/al/arcom_catastro.geojson
```

Endpoints:

```text
GET /arcom/concessions?bbox=-82,-6,-75,2&limit=120
GET /arcom/concession-lookup?lat=-3.015&lon=-78.48
```

El GeoPackage no lo sirve directamente API Central. Queda como archivo local en:

```text
/root/robiotec/arcom/arcom_catastro.gpkg
```

## OSINT

API Central tambien sirve las capas OSINT descargadas localmente. El router esta en:

```text
app/api/routes/osint.py
```

La lógica de lectura, cache y filtro por `bbox` esta en:

```text
app/services/osint_service.py
```

La API lee estos archivos por defecto:

```text
/root/robiotec/osint/osint_layers.geojson
/root/robiotec/osint/osint_descarga_reporte.json
```

Variables:

```text
OSINT_GEOJSON=/root/robiotec/osint/osint_layers.geojson
OSINT_REPORT=/root/robiotec/osint/osint_descarga_reporte.json
```

Endpoints:

```text
GET /osint/layers?bbox=-82,-6,-75,2&limit=2000&layer=all
GET /osint/report
```

El parametro `layer` filtra antes de responder. Puede ser `all`, `eventos`,
`gdo_point`, `upc_point`, `gdo_zone` o el `source` exacto del GeoJSON, por
ejemplo `eventos_operativos_ffoo`, `punto_interes_policias` o
`zonas_poligonos_gdo`. Las rutas de narcotrafico se consultan con
`layer=rutas_narcotrafico`.

Para mantener liviano el mapa, API Central reutiliza una instancia en memoria
para ARCOM y OSINT, calcula el bbox de cada feature una sola vez y responde solo
propiedades publicas necesarias para popups/estilos. OSINT no expone `raw` en
`/osint/layers`.
