# Robiotec

Sistema de videovigilancia, telemetria y administracion multi-organizacion para ROBIOTEC.

Estado de entrega: 2026-06-14. Este documento describe el arbol activo del repo, los servicios que se usan y las validaciones ejecutadas en esta pasada.

## Arquitectura

Robiotec esta compuesto por:

| Componente | Ruta | Tecnologia | Funcion |
| --- | --- | --- | --- |
| API Central | `apicentral/` | FastAPI, SQLAlchemy, PostgreSQL, MinIO | Autenticacion, usuarios, organizaciones, camaras, streams, telemetria, geocercas, eventos e ingest central. |
| Dashboard | `dashboard/` | FastAPI, HTML templates, CSS, JS | Interfaz web, proxy autenticado hacia API Central, mapa de flota, camaras, reportes, administracion y notificaciones. |
| MediaMTX | `mediamtx/` | MediaMTX | RTSP/RTMP/HLS/WebRTC para video. La API de control escucha localmente. |
| Migraciones | `db/sql/` | SQL PostgreSQL | Modelo SaaS, telemetria, reportes, geocercas, outbox y optimizaciones. |
| Servicios | `servicios/` | systemd helpers, scripts de arranque | Instalacion y operacion de API, dashboard, MediaMTX, descargas ARCOM/OSINT, retencion y workers remotos. |
| Datos ARCOM/OSINT | `arcom/`, `osint/` | Python, GeoJSON/GPKG/CSV | Capas geoespaciales usadas por el mapa. |
| Faces Gallery | `faces_gallery/` | Embeddings, FAISS, scripts operativos | Galeria de embeddings faciales consumida por Jetson mediante API central. |
| Artemis | `dashboard/back/app/services/artemis/` | Python background service | Integracion de telemetria vehicular Artemis embebida en el dashboard. |

## Arbol activo

```text
robiotec/
  apicentral/          API principal
  dashboard/           Interfaz web y proxy autenticado
  db/sql/              Migraciones SQL versionadas
  servicios/           Servicios systemd y scripts de operacion
  mediamtx/            Configuracion de streaming
  arcom/               Descarga/capas ARCOM
  osint/               Descarga/capas OSINT
  faces_gallery/       Embeddings faciales y scripts de sincronizacion
```

Se retiraron del entregable las piezas locales que no estaban integradas al runtime actual: `hunter/`, `creaciion_zona/`, `simuladores/`, notas operativas antiguas, backups sueltos, artefactos `.codex` y datos runtime versionados.

`faces_gallery/` se mantiene porque forma parte del runtime de reconocimiento facial. Los archivos pesados generados viven en `faces_gallery/data/` y no se versionan; la carpeta y sus scripts operativos si quedan documentados.

## Seguridad y acceso

Las credenciales no deben vivir en codigo, README ni logs. Los secretos se cargan por variables de entorno:

- API Central: `apicentral/.env`.
- Dashboard: `dashboard/.env`.
- MediaMTX: `mediamtx/.env`.
- Servicios: `servicios/.env.example` como plantilla.

Variables clave:

- `MASTER_USERNAME` y `MASTER_PASSWORD`: usuario master inicial.
- `JWT_SECRET_KEY`: firma JWT.
- `DATABASE_URL`: conexion PostgreSQL.
- `SECRET_ENCRYPTION_KEY`: cifrado de secretos de streams.
- `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`: acceso MinIO.
- `SERVICE_INGEST_TOKEN`: token para ingest remoto centralizado.
- `FACES_GALLERY_DIR`, `FACES_GALLERY_TOKEN`: carpeta y token para que Jetson descargue embeddings faciales desde API Central.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DEFAULT_CHAT_IDS`: Telegram.
- `SMTP_SENDER_EMAIL`, `SMTP_SENDER_PASSWORD`, `NOTIFICATION_DEFAULT_RECIPIENTS`: correo.

## Roles

El usuario `master` administra todo el sistema:

- Crea organizaciones.
- Crea administradores por organizacion.
- Crea operadores por organizacion.
- Gestiona roles globales y de organizacion.
- Ve y edita camaras, vehiculos, drones, geocercas, reportes y configuraciones.

Roles operativos:

| Rol | Alcance |
| --- | --- |
| `admin` | Administra recursos de su organizacion. |
| `viewer` | Visualiza todo lo autorizado sin editar. |
| `operator_cameras` | Acceso operativo a camaras. |
| `operator_map` | Acceso operativo a mapa vehicular, rutas y kilometraje. |

El dashboard decide la ruta inicial y permisos visibles a partir de `/auth/me` y de los permisos calculados por API Central.

## Funcionalidades

### Administracion

La pantalla principal de administracion esta en `/registros` y unifica:

- Organizaciones.
- Usuarios.
- Roles.
- Camaras.
- Vehiculos.

Los recursos se filtran por organizacion. El master tiene alcance global; usuarios no master quedan limitados a su `company_id`.

### Mapa y flota

El mapa de flota:

- Inicia centrado en Ecuador.
- Usa `vehicle_source_id` estable para seleccionar vehiculos y evitar mezclar marcadores.
- Dibuja ruta historica por vehiculo con `/api/telemetry/history`.
- Consulta kilometraje diario, mensual o por rango con endpoints optimizados.
- Permite geocercas tipo poligono con nombre, color y guardado desde una ventana flotante.

Tablas principales:

- `vehicles`
- `vehicle_telemetry`
- `geofences`
- `vehicle_geofence_states`
- `geofence_alerts`

### Camaras y video

El flujo de camaras usa:

- `cameras`
- `rboxes`
- `stream_configs`
- `stream_paths`
- `stream_templates`
- `stream_access_tokens`
- `device_publish_tokens`

MediaMTX publica video y API Central valida permisos para streams. La API de MediaMTX queda local; los puertos de streaming publicos se exponen por diseno operativo.

### Eventos y evidencias

Los eventos se consultan desde:

- `camera_event_history`
- `camera_alert_outbox`
- MinIO para evidencias y clips.

El dashboard sirve crops/videos bajo demanda y mantiene cache local temporal en `dashboard/back/app/data/`, ignorado por git.

### Faces Gallery

La galeria local de embeddings se sirve desde API Central con token dedicado:

- `GET /faces-gallery/manifest`
- `GET /faces-gallery/metadata`
- `GET /faces-gallery/files/{filename}`

Por el proxy del dashboard tambien queda disponible como `/api/faces-gallery/...`. Archivos permitidos: `embeddings.npz`, `gallery.faiss`, `metadata.json`, `idx_to_cedula.json`, `state.json` y `version`.

Las Jetson deben usar `X-Robiotec-Faces-Token` o `Authorization: Bearer <token>`. Si `FACES_GALLERY_TOKEN` esta vacio, la API responde `faces_gallery_disabled`.

### Reportes

Reportes activos:

- Personas por dia.
- Persona individual.
- Sesiones por rango.
- Resumen mensual.
- Placas y exportacion CSV.
- Kilometraje por vehiculo y por flota.

Las consultas de kilometraje usan agregacion por rango y limites de fechas para no bloquear el dashboard en periodos largos.

### Ingest remoto 10.0.0.2

El worker remoto de media/eventos publica contra la API central por `/api/ingest` usando token de servicio. No debe escribir directo a PostgreSQL ni MinIO desde el host remoto.

El orquestador remoto consulta la inferencia que debe ejecutar desde:

- `GET /api/orchestrator/inference-configs`
- `GET /api/orchestrator/inference-configs/{camera_key}`

Ambos endpoints usan `X-Robiotec-Ingest-Token` o `Authorization: Bearer <SERVICE_INGEST_TOKEN>`. Si una camara responde `hacer_inferencia=false` o `inference_type=inactiva`, el orquestador debe detener cualquier inferencia activa para esa camara.

## Base de datos

Tablas detectadas en produccion:

```text
areas
camera_alert_outbox
camera_event_history
camera_inference_view_requests
cameras
companies
device_publish_tokens
drone_dji_configs
drone_robiotec_configs
drone_telemetry
drones
geofence_alerts
geofences
notification_email_recipients
notification_telegram_chat_ids
rboxes
remote_manifest_cursors
roles
stream_access_tokens
stream_configs
stream_paths
stream_templates
user_areas
user_roles
users
vehicle_geofence_states
vehicle_telemetry
vehicles
```

Migracion aplicada para flota/geocercas:

- `db/sql/17_create_fleet_geofences.sql`

Optimizacion disponible para reportes de kilometraje:

- `db/sql/18_optimize_vehicle_km_reports.sql`

## Servicios

Servicios residentes:

- `robiotec-apicentral.service`
- `robiotec-django.service`
- `robiotec-celery.service`
- `robiotec-celerybeat.service`
- `robiotec-mediamtx.service`
- `postgresql`
- `minio`

Tareas programadas o one-shot:

- `robiotec-arcom-download.service`
- `robiotec-osint-download.service`
- `robiotec-retention-cleanup.service`
- `robiotec-log-cleaner.service`
- `robiotec-plate-lookup-sync.service`
- `robiotec-state-camera-sync.service`

Puertos locales verificados:

- API Central: `127.0.0.1:8003`
- Dashboard principal Django: `127.0.0.1:8020`
- PostgreSQL: `127.0.0.1:5432`
- MinIO: `127.0.0.1:9000`, `127.0.0.1:9001`
- MediaMTX API: `127.0.0.1:9997`

Puertos publicos esperados:

- Nginx: `80`, `443`
- MediaMTX streaming: `1935`, `8554`, `8888`, `8889`, `8890`, UDP `8189`, UDP `8000`, UDP `8001`

## Comandos de operacion

Instalar o actualizar units:

```bash
sudo ./servicios/install-systemd.sh
```

Aplicar migraciones SQL:

```bash
set -a
. apicentral/.env
set +a
PSQL_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f db/sql/17_create_fleet_geofences.sql
```

Reiniciar servicios principales:

```bash
sudo systemctl restart robiotec-django.service robiotec-celery.service robiotec-celerybeat.service robiotec-apicentral.service robiotec-mediamtx.service
```

Ver estado:

```bash
systemctl is-active robiotec-django.service robiotec-celery.service robiotec-celerybeat.service robiotec-apicentral.service robiotec-mediamtx.service postgresql minio
```

## Validaciones ejecutadas

```bash
dashboard/.venv/bin/python -m py_compile dashboard/back/app/application.py dashboard/back/app/routers/data.py dashboard/back/app/routers/org.py dashboard/back/app/context.py dashboard/back/app/domain/vehicles/telemetry.py dashboard/back/app/domain/device_catalog.py dashboard/back/app/routers/events.py dashboard/back/app/routers/reports.py
apicentral/.venv/bin/python -m py_compile apicentral/app/api/routes/telemetry.py apicentral/app/api/routes/admin.py apicentral/app/api/routes/auth.py apicentral/app/api/routes/ingest.py apicentral/app/services/fleet.py apicentral/app/services/permission_service.py apicentral/app/main.py
apicentral/.venv/bin/python -m py_compile apicentral/app/api/routes/faces_gallery.py
node --check dashboard/front/static/web_app.js
node --check dashboard/front/static/cameras_page_viewer.js
PYTHONPATH=dashboard dashboard/.venv/bin/python -m unittest discover -s dashboard/back/tests -v
```

Smoke tests autenticados:

- Login master: `200`.
- `/api/auth/session`: `200`.
- `/api/organizations`: `200`.
- `/api/users`: `200`.
- `/api/user-roles`: `200`.
- `/api/cameras`: `200`.
- `/api/vehicle-registry?limit=5`: `200`.
- `/api/geofences`: `200`.
- `/api/telemetry`: `200`.
- `/api/objetivos/DRONE`: `200`.
- `/api/reports/overview?from_date=2026-06-01&to_date=2026-06-14`: `200`.
- `/mapa`: `200`.
- `/registros`: `200`.
- `/notificaciones`: `200`.

Prueba de geocerca:

- Crear geocerca temporal: `201`.
- Eliminar geocerca temporal: `200`.

## Notas de produccion

- No versionar evidencias, clips, crops, caches, backups ni credenciales.
- Mantener PostgreSQL, MinIO, API Central y Dashboard en loopback detras de Nginx.
- Mantener la exposicion publica solo para Nginx y puertos de streaming necesarios.
- Revisar logs de systemd despues de cada despliegue.
- Ejecutar migraciones SQL con `ON_ERROR_STOP=1`.
