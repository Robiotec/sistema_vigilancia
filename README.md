# Sistema de videovigilancia inteligente Robiotec

Arquitectura modular para una sola VM:

- `apicentralt`: API FastAPI, autenticacion, autorizacion, Telemetria y control de streams.
- `db`: scripts SQL iniciales de PostgreSQL.
- `mediamtx`: configuracion base de MediaMTX con autenticacion HTTP contra la API.
- `dashboard`: frontend separado de la API.
- `arcom`: descarga local del Catastro Minero Nacional y archivos generados para capas geograficas.
- `osint`: descarga local de capas OSINT externas y GeoJSON normalizado para el mapa.
- `servicios`: workers, agentes y simuladores auxiliares.

## Mapa ARCOM

La capa `Capa ARCOM` del mapa se alimenta del Catastro Minero Nacional.
La responsabilidad esta separada asi:

```text
arcom/download_arcom.py
  Descarga desde ArcGIS REST oficial de ARCOM y genera archivos locales.

arcom/arcom_catastro.gpkg
  GeoPackage local generado. Util para GIS, respaldo y uso externo.

arcom/arcom_catastro.geojson
  GeoJSON local generado. API Central lo lee para servir al mapa.

apicentral/app/services/arcom_service.py
  Lee el GeoJSON, filtra por bbox y detecta si una coordenada cae dentro de una concesion.

apicentral/app/api/routes/arcom.py
  Router publico interno de API Central:
  GET /arcom/concessions
  GET /arcom/concession-lookup

dashboard/back/app/application.py
  Solo conserva proxy /api/arcom/... hacia API Central para que el frontend use rutas relativas.

dashboard/front/static/web_app.js
  Consume /api/arcom/concessions y /api/arcom/concession-lookup para pintar la capa y detectar concesiones.

servicios/arcom/
  Unidad systemd, timer semanal, scripts operativos y logs de descarga.
```

Flujo operativo:

```text
ARCOM oficial
  -> servicio semanal robiotec-arcom-download.timer
  -> arcom/arcom_catastro.geojson + arcom/arcom_catastro.gpkg
  -> API Central /arcom/...
  -> Dashboard /api/arcom/... proxy
  -> mapa Leaflet
```

## Mapa OSINT

La capa `Capa OSINT` descarga diariamente datos publicos de
`https://vectorinternational.ai/api`, los normaliza localmente y los publica
desde API Central.

```text
osint/download_osint.py
  Descarga endpoints OSINT y genera archivos locales.

osint/osint_raw/*.json
  Respuestas crudas por endpoint.

osint/osint_layers.geojson
  GeoJSON normalizado. API Central lo lee para servir al mapa.

apicentral/app/services/osint_service.py
  Lee el GeoJSON y filtra features por bbox.

apicentral/app/api/routes/osint.py
  Router de API Central:
  GET /osint/layers
  GET /osint/report

dashboard/back/app/application.py
  Proxy /api/osint/... hacia API Central.

dashboard/front/static/web_app.js
  Consume /api/osint/layers cuando el usuario activa `Capa OSINT`.

servicios/osint/
  Unidad systemd, timer diario, scripts operativos y logs de descarga.
```

## Requisitos

- Python 3.12+
- `uv`
- PostgreSQL 15+
- MediaMTX

## Instalacion base

```bash
cd apicentral
uv init --app --name apicentral
uv add fastapi uvicorn sqlalchemy psycopg[binary] pydantic-settings python-jose[cryptography] passlib[bcrypt] httpx python-multipart
uv sync
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8003
```

Ejecutar SQL inicial:

```bash
psql -U postgres -v app_password='<password_seguro>' -f db/sql/00_create_database.sql
psql -U postgres -d robiotec_vms -f db/sql/01_create_extensions.sql
psql -U postgres -d robiotec_vms -f db/sql/02_create_tables.sql
psql -U postgres -d robiotec_vms -f db/sql/03_create_default_roles.sql
```

Para crear el usuario master por SQL, genere primero un hash bcrypt y paselo como variable:

```bash
psql -U postgres -d robiotec_vms -v master_password_hash='<bcrypt_hash>' -f db/sql/04_create_master_user.sql
```

La API tambien crea o corrige el usuario master al arrancar. El usuario master unico para API, base de datos funcional y dashboard es `robiotec` con clave `Robiotec@2026`.

## Seguridad operativa

- No exponer `MEDIAMTX_API_URL` fuera de localhost o red privada.
- No publicar archivos `.env`.
- El dashboard nunca debe recibir URLs RTSP reales.
- MediaMTX debe llamar a `POST /mediamtx/auth` para `publish` y `read`.
