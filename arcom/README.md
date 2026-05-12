# ARCOM

Esta carpeta contiene la descarga local del Catastro Minero Nacional.

## Archivos Importantes

```text
download_arcom.py
  Script principal. Descarga datos desde el ArcGIS REST oficial de ARCOM.

arcom_catastro.geojson
  GeoJSON generado. API Central lo lee para responder las consultas del mapa.

arcom_catastro.gpkg
  GeoPackage generado. Archivo GIS local para respaldo, inspeccion o uso externo.

arcom_catastro_atributos.csv
  CSV generado con atributos.

arcom_descarga_reporte.json
  Reporte de la ultima descarga: fuente, conteos, faltantes y tamanos.

arcom_ids_faltantes.txt
  Solo aparece si la descarga queda incompleta.
```

## Fuente Oficial

Por defecto se descarga desde:

```text
https://geovisorm.controlrecursosyenergia.gob.ec/arcgis/rest/services/Concesiones/CatastroMineroNacional_PSAD56/MapServer/0
```

La URL se puede cambiar con:

```text
ARCOM_LAYER_URL=...
```

## Ejecucion Manual

Desde el repo:

```bash
/root/robiotec/servicios/arcom/scripts/download.sh
```

O directamente:

```bash
cd /root/robiotec/arcom
ARCOM_OUT_DIR=/root/robiotec/arcom /root/.local/bin/uv run --with requests python download_arcom.py
```

Requiere:

```text
ogr2ogr
uv
requests
```

En Ubuntu, `ogr2ogr` viene de:

```bash
apt-get install -y gdal-bin
```

## Servicio Semanal

La unidad esta en:

```text
/root/robiotec/servicios/arcom/systemd/robiotec-arcom-download.service
/root/robiotec/servicios/arcom/systemd/robiotec-arcom-download.timer
```

El timer ejecuta la descarga cada lunes a las `04:00 UTC`.

Comandos utiles:

```bash
systemctl start robiotec-arcom-download.service
systemctl status robiotec-arcom-download.service
systemctl status robiotec-arcom-download.timer
/root/robiotec/servicios/arcom/scripts/logs.sh
```

## Consumo En La Plataforma

API Central lee `arcom_catastro.geojson` desde:

```text
apicentral/app/services/arcom_service.py
```

Y publica:

```text
GET /arcom/concessions?bbox=west,south,east,north&limit=120
GET /arcom/concession-lookup?lat=-3.015&lon=-78.48
```

El dashboard solo conserva proxy:

```text
GET /api/arcom/concessions
GET /api/arcom/concession-lookup
```
