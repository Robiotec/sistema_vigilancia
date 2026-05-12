# OSINT

Descarga local de capas publicas usadas por Vector International OSINT 360.

## Archivos

```text
download_osint.py
  Descarga endpoints de Vector y genera archivos locales.

osint_raw/*.json
  Respuestas crudas por endpoint.

osint_layers.geojson
  GeoJSON normalizado que API Central usa para el mapa. No incluye el campo
  `raw`; las respuestas completas se conservan solo en osint_raw/*.json para
  que la carga de API/mapa sea mas liviana.

osint_descarga_reporte.json
  Resumen de la ultima descarga.
```

## Endpoints Fuente

Base:

```text
https://vectorinternational.ai/api
```

Endpoints descargados:

```text
/punto-interes/gdos
/zonas/poligonos-gdo
/rutas-narcotrafico
/punto-interes/policias
/eventos/eventos-capas-id?id_tipo_evento=UNIDADES_FFAA
/eventos/eventos-capas-id?id_tipo_evento=RESIDENCIAS_CRIMINALES
/eventos/eventos-capas-id?id_tipo_evento=MARCADORES_CRIMINALES
/eventos/eventos-capas-id?id_tipo_evento=OPERATIVOS_FFOO
/eventos/eventos-capas-id?id_tipo_evento=HOMICIDO_SICARIATO
/eventos/eventos-capas-id?id_tipo_evento=PASO_ILEGAL
/eventos/eventos-capas-id?id_tipo_evento=PASO_OFICIAL
/eventos/eventos-capas-id?id_tipo_evento=MINERIA_ILEGAL
/zonas/tipos-zonas
/parametros
/eventos/tipos-eventos
```

`/eventos/tipos-eventos` se descarga como catalogo para saber que tipos existen;
no se pinta como capa directa en el mapa.

Nota: `punto-interes/gdos` trae una lista `zonas` con polígonos de provincias
como Pastaza. Esos polígonos no se publican en `osint_layers.geojson`; solo se
mantienen los puntos GDO y las zonas GDO reales de `/zonas/poligonos-gdo`.
Tambien se excluye cualquier zona con `id=1` o nombre `Cantones`.

## Ejecucion

```bash
/root/robiotec/servicios/osint/scripts/download.sh
```

API Central sirve el resultado desde:

```text
GET /osint/layers?bbox=west,south,east,north&limit=2000&layer=all
GET /osint/report
```

`layer` puede ser `all` o una fuente concreta como
`eventos_operativos_ffoo`, `eventos_marcadores_criminales`,
`eventos_homicido_sicariato`, `punto_interes_policias`,
`punto_interes_gdos.puntos`, `zonas_poligonos_gdo` o `rutas_narcotrafico`.
