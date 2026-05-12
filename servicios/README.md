# Servicios Robiotec

Esta carpeta concentra las unidades systemd, scripts operativos y logs de los servicios de la VM.

## Servicios principales

- `apicentral`: API FastAPI en puerto `8003`.
- `dashboard`: dashboard FastAPI/Jinja en puerto `8010`.
- `mediamtx`: servidor MediaMTX.
- `arcom`: descarga semanal del Catastro Minero Nacional y genera `arcom/arcom_catastro.gpkg`.
- `osint`: descarga diaria de capas OSINT y genera `osint/osint_layers.geojson`.
- `log-cleaner`: limpieza semanal de logs cada lunes a las `03:00`.

Cada servicio tiene esta estructura:

- `systemd`: archivos `.service` y `.timer` cuando aplica.
- `scripts`: comandos `.sh` de arranque, parada, estado y logs.
- `logs`: salida persistente del servicio.

## Instalar unidades systemd

```bash
cd /root/robiotec/servicios
./install-systemd.sh
systemctl start robiotec-apicentral robiotec-dashboard robiotec-mediamtx
systemctl start robiotec-arcom-download.timer robiotec-osint-download.timer robiotec-log-cleaner.timer
```

## Ver logs

```bash
/root/robiotec/servicios/apicentral/scripts/logs.sh
/root/robiotec/servicios/dashboard/scripts/logs.sh
/root/robiotec/servicios/mediamtx/scripts/logs.sh
/root/robiotec/servicios/arcom/scripts/logs.sh
/root/robiotec/servicios/osint/scripts/logs.sh
/root/robiotec/servicios/log-cleaner/scripts/logs.sh
```

## ARCOM

El timer `robiotec-arcom-download.timer` corre cada lunes a las `04:00` y ejecuta
`arcom/download_arcom.py`. La descarga deja el GeoPackage en
`/root/robiotec/arcom/arcom_catastro.gpkg` y el GeoJSON auxiliar en
`/root/robiotec/arcom/arcom_catastro.geojson`.

API Central publica esos datos en:

- `GET /arcom/concessions?bbox=west,south,east,north&limit=120`
- `GET /arcom/concession-lookup?lat=-3.015&lon=-78.48`

El dashboard conserva sus rutas `/api/arcom/...` como proxy hacia API Central,
para que la capa visible `Capa ARCOM` siga funcionando en el mapa.

Requisitos del host:

- `ogr2ogr` disponible en el sistema, normalmente desde GDAL.
- `uv` en `/root/.local/bin/uv`, o definir `UV_BIN` en `servicios/.env`.

Ejecucion manual:

```bash
/root/robiotec/servicios/arcom/scripts/download.sh
systemctl start robiotec-arcom-download.service
```

## OSINT

El timer `robiotec-osint-download.timer` corre todos los dias a las `04:30 UTC`.
Ejecuta `osint/download_osint.py`, guarda respuestas crudas en
`/root/robiotec/osint/osint_raw/` y genera:

```text
/root/robiotec/osint/osint_layers.geojson
/root/robiotec/osint/osint_descarga_reporte.json
```

API Central publica esos datos en:

- `GET /osint/layers?bbox=west,south,east,north&limit=2000&layer=all`
- `GET /osint/report`

El dashboard conserva `/api/osint/...` como proxy y muestra la capa desde una
lista desplegable: `Nada`, `Todo OSINT` o una fuente/clase concreta.

La normalizacion excluye los polígonos provinciales que vienen dentro de
`punto-interes/gdos.zonas` y conserva solo puntos GDO, UPC, zonas GDO reales y
eventos configurados como Marcadores Criminales, Operativos FFOO,
Homicidios/Sicariatos, pasos fronterizos, Mineria Ilegal y Unidades FFAA.

Ejecucion manual:

```bash
/root/robiotec/servicios/osint/scripts/download.sh
systemctl start robiotec-osint-download.service
```

## Carpetas auxiliares

- `rbox_agent`: publicacion y sincronizacion desde R-Box.
- `inferencia`: workers de vision o analitica.
- `telemetry_simulator`: pruebas de telemetria de drones y vehiculos.
- `monitoring`: monitoreo interno y health checks.
