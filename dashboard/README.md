# Dashboard

Frontend separado de la API central. Implementado con FastAPI + Jinja servido con `uv`, tomando como referencia visual el dashboard `Robiotec/Mili`: paleta oscura, naranja Robiotec, sidebar compacto, login operativo y paneles de mando.

## Estructura

```text
dashboard/
  back/        Backend FastAPI, servicios, dominio y clases base/hijas.
  front/       Templates, CSS, JS, iconos y assets.
  app/         Adaptador compatible con uvicorn app.main:app.
```

Dominios principales:

```text
back/app/domain/empresa.py                  Empresa.
back/app/domain/rbox.py                     RBox.
back/app/domain/cameras/base.py             Camara.
back/app/domain/cameras/static_camera.py    camestatica.
back/app/domain/cameras/custom_camera.py    CamaraPerso.
back/app/domain/cameras/ptz_camera.py       camaraptz y APIControlptz.
back/app/domain/cameras/car_camera.py       camcar.
back/app/domain/vehicles/base.py            vehiculo.
back/app/domain/vehicles/telemetry.py       TelemetriaVehiculo.
back/app/domain/drones/base.py              DRON.
back/app/domain/drones/robiotec.py          robio_dron.
back/app/domain/drones/dji.py               dron_dji.
back/app/domain/drones/telemetry.py         TelemetriaDron.
back/app/domain/streaming/stream_config.py  StreamConfig.
back/app/core/helpers.py                    Funciones de apoyo compartidas.
back/app/application.py                     Ensamblado FastAPI y rutas.
back/app/main.py                            Punto de entrada minimo.
```

## Ejecutar

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8010
```

También se puede ejecutar apuntando directamente al backend refactorizado:

```bash
uv run uvicorn back.app.main:app --host 0.0.0.0 --port 8010
```

URL por defecto:

```bash
http://127.0.0.1:8010
```

Flujo esperado:

1. Login contra `POST /auth/login`.
2. Guardar JWT en memoria o almacenamiento seguro segun despliegue.
3. Consultar `GET /streams/{path}/status`.
4. Si `online=false`, mostrar `Video no disponible`.
5. Si `online=true`, solicitar `POST /stream/token/{path}`.
6. Abrir WHEP/WebRTC usando solo `viewer_url`.

No exponer URLs RTSP reales ni la API interna de MediaMTX.

## ARCOM En El Mapa

El dashboard no procesa ARCOM directamente. La lógica real vive en API Central:

```text
apicentral/app/api/routes/arcom.py
apicentral/app/services/arcom_service.py
```

El dashboard mantiene solo estas rutas proxy para el frontend:

```text
GET /api/arcom/concessions
GET /api/arcom/concession-lookup
```

Esas rutas estan en:

```text
dashboard/back/app/application.py
```

El frontend del mapa llama a esas rutas relativas desde:

```text
dashboard/front/static/web_app.js
```

Si se quiere eliminar el proxy en el futuro, hay que cambiar el JS para llamar
directamente a API Central y revisar CORS/base URL del navegador.

## OSINT En El Mapa

El dashboard tampoco procesa OSINT directamente. La lógica real vive en:

```text
apicentral/app/api/routes/osint.py
apicentral/app/services/osint_service.py
```

El dashboard conserva proxy:

```text
GET /api/osint/layers
GET /api/osint/report
```

La opcion visible para el usuario esta en:

```text
dashboard/front/templates/partials/telemetry_map_workbench.html
```

La lógica Leaflet de la capa esta en:

```text
dashboard/front/static/web_app.js
```

La capa OSINT se carga por viewport, igual que ARCOM: el frontend envia el
`bbox` visible a `/api/osint/layers` despues de mover o acercar el mapa. La
opcion del mapa es una lista desplegable para elegir `Nada`, `Todo OSINT` o una
clase/fuente concreta, por ejemplo `Operativos FFOO`, `Marcadores Criminales`,
`Rutas Narcotrafico`, `UPC / Policia`, `Puntos GDO` o `Zonas GDO`. El mapa de
telemetria inicia centrado en Ecuador (`[-1.831239, -78.183406]`, zoom 7).
El bbox se redondea antes de consultar para evitar recargas por movimientos
minimos del mapa.
