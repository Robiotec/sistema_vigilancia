# Robiotec Plataforma Django

Base nueva para migrar Robiotec a Django, Django REST Framework, PostgreSQL, Celery y TypeScript modular.

Esta carpeta convive con `apicentral/`, `dashboard/` y `servicios/` mientras se migra por etapas. No reemplaza los servicios actuales hasta que cada modulo este validado.

## Stack

- Django 5.2 LTS
- Django REST Framework
- PostgreSQL
- Celery + Redis
- Gunicorn + systemd
- Bootstrap 5
- TypeScript modular compilado con Vite

## Estructura

- `config/`: configuracion Django, ASGI/WSGI, URLs y Celery.
- `apps/core/`: utilidades compartidas, health checks y clases base.
- `apps/organizations/`: empresas y areas.
- `apps/accounts/`: usuarios y roles legacy.
- `apps/devices/`: camaras, RBox, vehiculos y drones.
- `apps/streaming/`: MediaMTX, paths y configuraciones de stream.
- `apps/fleet/`: telemetria vehicular y kilometraje.
- `apps/geofences/`: geocercas, estados y eventos.
- `apps/alerts/`: eventos, destinatarios y envios.
- `apps/reports/`: reportes diarios y tareas programadas.
- `apps/frontend/`: templates/static del dashboard nuevo.
- `frontend/`: TypeScript compartido del dashboard.
- `systemd/`: unidades para produccion sin Docker.

## Arranque local

```bash
cd /root/robiotec/plataforma
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py check
python manage.py runserver 0.0.0.0:8020
```

## Frontend

```bash
cd /root/robiotec/plataforma/frontend
npm install
npm run build
```

El build escribe los assets en `apps/frontend/static/dashboard/`.

## Produccion con systemd

Copiar las unidades de `systemd/` a `/etc/systemd/system/`, ajustar rutas/usuario si cambia el servidor y activar:

```bash
systemctl daemon-reload
systemctl enable --now robiotec-django.service
systemctl enable --now robiotec-celery.service
systemctl enable --now robiotec-celerybeat.service
```

La migracion debe hacerse por modulos. Primero se conectan APIs de solo lectura a las tablas existentes; luego se reemplazan pantallas y procesos uno por uno.

## Estado actual en este servidor

Servicios levantados:

```bash
systemctl status robiotec-django.service
systemctl status robiotec-celery.service
systemctl status robiotec-celerybeat.service
```

URLs locales:

- Dashboard Django: `http://127.0.0.1:8020/`
- Login Django: `http://127.0.0.1:8020/login/`
- Administracion camaras/RBox: `http://127.0.0.1:8020/administracion/dispositivos/`
- Centro de camaras: `http://127.0.0.1:8020/camaras/`
- Mapa y recorridos: `http://127.0.0.1:8020/mapa/`
- Geocercas: `http://127.0.0.1:8020/geocercas/`
- Gestion de kilometros: `http://127.0.0.1:8020/gestion-kilometros/`
- Notificaciones: `http://127.0.0.1:8020/notificaciones/`
- Eventos de camaras e IA: `http://127.0.0.1:8020/eventos/`
- Reportes de detecciones: `http://127.0.0.1:8020/reportes/`
- Usuarios y organizaciones: `http://127.0.0.1:8020/usuarios/`
- Perfil de usuario: `http://127.0.0.1:8020/perfil/`
- Servicios externos: `http://127.0.0.1:8020/servicios/`
- Health check: `http://127.0.0.1:8020/health/`
- API camaras: `http://127.0.0.1:8020/api/v1/devices/cameras/`

URLs publicas por Nginx:

- Dashboard principal actual: `https://robio-ai.com/` apunta a `127.0.0.1:8020`.
- Dashboard Django de pruebas: `https://beta.robio-ai.com/` tambien apunta a `127.0.0.1:8020`.
- MediaMTX sigue publicado en `https://robio-ai.com/mediamtx/`.

Modo de despliegue actual:

- Django corre en `8020`, comparte la misma base PostgreSQL y sirve el dominio publico principal, `beta.robio-ai.com` y proxy interno.
- El dashboard FastAPI/Jinja legacy ya no atiende el dominio publico ni participa del arranque systemd.
- MediaMTX sigue publicado en `https://robio-ai.com/mediamtx/`.
- El frontend Django usa Bootstrap 5 con TypeScript modular, pero la carcasa visual copia el dashboard actual: sidebar colapsable, login oscuro, paneles, listas y modales Robiotec.
- Gunicorn en `8020` no sirve archivos estaticos por si solo (no tiene Whitenoise). Detras de Nginx (`beta.robio-ai.com` o el `location /static/` local) esto no es un problema; accediendo directo a `127.0.0.1:8020` sin proxy, `/static/...` da 404 y la pantalla se ve sin CSS/JS. Pendiente decidir si se agrega Whitenoise para que el acceso directo tambien funcione.

Validaciones ejecutadas:

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py test apps.devices.tests --settings=config.settings.test
python manage.py test apps.alerts.tests apps.devices.tests apps.fleet.tests apps.reports.tests --settings=config.settings.test
python manage.py test apps.accounts.tests apps.alerts.tests apps.devices.tests apps.fleet.tests apps.reports.tests apps.streaming.tests --settings=config.settings.test
python manage.py test apps.accounts.tests apps.alerts.tests apps.devices.tests apps.fleet.tests apps.geofences.tests apps.reports.tests apps.streaming.tests --settings=config.settings.test
python manage.py test apps.accounts.tests apps.alerts.tests apps.devices.tests apps.fleet.tests apps.geofences.tests apps.operations.tests apps.reports.tests apps.streaming.tests --settings=config.settings.test
npm run typecheck
npm run build
python manage.py collectstatic --noinput
```

## Auditoria visual y funcional vs. dashboard legacy (2026-07-01)

Primera pasada de pruebas manuales (login + navegacion autenticada por las 12 pantallas, con capturas y comparacion directa contra el dashboard legacy). Resultado: el "esqueleto" (sidebar oscura, acento naranja/rojo, cards, tipografia) es consistente entre pantallas del dashboard nuevo, pero varias pantallas son mas simples que su equivalente legacy y les faltan funciones reales, no solo estilo.

### Bugs encontrados y corregidos en esta sesion

- **Sidebar y acceso HTML no respetaban roles legacy**: cerrado. El legacy filtra menu, pagina inicial y acceso por permisos derivados de `master/admin/viewer/operator_cameras/operator_map`; Django mostraba todos los enlaces fijos en `base.html` y las vistas solo exigian sesion. Se agrego `LegacyRoleService.page_permissions_for_user()`, redireccion por rol en las vistas HTML y sidebar/index filtrados desde backend. `/admin/` ya no aparece como enlace normal del dashboard.
- **Estaticos 404 accediendo directo a `:8020`**: cerrado con fallback Django controlado por `ROBIOTEC_SERVE_STATIC_DIRECT` (default activo). Nginx (`beta.robio-ai.com` y `:8021` local) sigue siendo la ruta preferida para servir `/static/`, pero el puerto `8020` ya no queda sin CSS/JS si se abre directo.
- **Envio automatico de reporte diario de kilometros quedo encendido sin validacion real** (`FleetDailyReportSetting.enabled=True` con SMTP nunca probado). Se desactivo (`enabled=False`). El plan de migracion exige probar SMTP real antes de reactivarlo.
- **Toast de error duplicado en login invalido**: `ApiClient` ya dispara un toast global en cualquier respuesta no-ok y `LoginPage.submit()` disparaba otro propio. Corregido pasando `{ silent: true }` en el POST de login (`frontend/src/pages/login.ts`).
- **Video en vivo del Centro de camaras quedaba en blanco**: el visor apuntaba un `<iframe>` directo a la URL WebRTC cruda de MediaMTX (`/mediamtx/{path}/`), que en este servidor no sirve una pagina HTML embebible (solo WHEP, que rechaza GET) y ademas queda bloqueada por `X-Frame-Options: SAMEORIGIN` en origenes cruzados. Se reemplazo por el mismo patron que usa el dashboard legacy: un endpoint propio (`GET /api/v1/streaming/camera-viewer/<camera_id>/snapshot/`) que pide un frame a MediaMTX por RTSP local (`rtsp://127.0.0.1:8554/{path}`, no el RTSP original de la camara que en camaras con RBox vive en una LAN privada inalcanzable desde este servidor) via `ffmpeg` y lo sirve como JPEG. El frontend (`camera-viewer.ts`) ahora usa un `<img>` que se refresca cada 4s en vez del iframe.

### Brecha de estilo/funcionalidad pendiente (no son bugs, son features del legacy sin migrar)

**Login** (`/login/` nuevo vs `/login` legacy): cerrado. Replica la composicion oscura del legacy con panel izquierdo, logos graficos reales, tarjetas de features, toggle mostrar/ocultar contrasena y seccion "Perfiles rapidos" (Supervisor/Analista), manteniendo el endpoint Django `/api/v1/auth/login/`.

**Mapa y recorridos** (`/mapa/` nuevo vs `/mapa` legacy) — **cerrado en esta sesion**, salvo lo marcado abajo:
- Selector de basemap (Principal/Satelital/Oscuro/Relieve): agregado, mismos tiles que el legacy (Esri World_Street_Map, Esri World_Imagery + labels, CartoDB dark_all, Esri World_Topo_Map). El "Principal" nuevo ya no es el OSM blanco que rompia el tema oscuro.
- Capa ARCOM (checkbox, concesiones mineras): agregada. Nuevo endpoint `GET /api/v1/fleet/geointel/arcom/concessions/?bbox=...` en `apps/fleet/geointel.py` que hace de proxy autenticado hacia apicentral (`http://127.0.0.1:8003/arcom/concessions`, que a su vez lee `/root/robiotec/arcom/arcom_catastro.geojson`). No se duplico el filtrado geoespacial en Django, se reusa el servicio existente.
- Selector OSINT (12 categorias, mismos valores que el legacy: `eventos_homicido_sicariato`, `eventos_operativos_ffoo`, `eventos_marcadores_criminales`, `eventos_mineria_ilegal`, `eventos_paso_ilegal`, `eventos_paso_oficial`, `eventos_unidades_ffaa`, `rutas_narcotrafico`, `punto_interes_policias`, `punto_interes_gdos.puntos`, `zonas_poligonos_gdo`, mas `all`/`none`): agregado. Mismo patron de proxy, `GET /api/v1/fleet/geointel/osint/layers/?bbox=...&layer=...` hacia `http://127.0.0.1:8003/osint/layers`. Iconos por `url_icono` cuando la feature lo trae, fallback a circulo de color.
- Recentrar, Exportar rutas (CSV del recorrido cargado) y Clear: agregados.
- **Trafico Aereo: no se replico a proposito.** El endpoint legacy (`/api/aircraft/viewport` en `dashboard/back/app/routers/data.py:158-160`) esta stub, siempre devuelve `{"aircraft": [], "source": "not_configured"}` — el toggle existe en la UI vieja pero no muestra trafico real hoy. No hay nada funcional que migrar todavia.
- **Nueva zona y edicion de geocercas directo sobre el mapa: cerrado.** Se agrego `leaflet-draw` (+`@types/leaflet-draw`). Boton "Nueva zona" + selector Poligono/Circulo activan el modo de dibujo; al cerrar la forma se abre un panel flotante movible (Nombre + Color) que no tapa la edicion de puntos. Las geocercas existentes exponen Editar/Eliminar en el popup; editar habilita los handles de vertices/circulo y guarda con `PUT /api/v1/geofences/geofences/<id>/` usando el mismo contrato de payload del CRUD por formulario.
  - Bug encontrado y corregido en el camino: mientras el modo dibujo esta activo, un click cerca de un vehiculo disparaba su seleccion (`selectDevice`) y hacia zoom automatico al vehiculo, arruinando el poligono en progreso. Los marcadores ahora ignoran el click si `drawHandler` esta activo.
- **Drones en el mapa**: agregado. `DroneTelemetry` (tabla `drone_telemetry`, ya existia el modelo Django pero no se usaba en el mapa) ahora se mezcla con `VehicleTelemetry` en `FleetMapService.latest_locations()`. Nuevo endpoint `GET /api/v1/fleet/drones/<id>/route/` simetrico al de vehiculos.
- **Iconos por tipo y color por frescura**: los marcadores ya no son un circulo generico. Carros usan un icono de auto, drones un icono de dron (SVG inline via `L.divIcon`), y ambos se pintan **verde si hay telemetria de la ultima hora, rojo si no** (`FleetMapService._freshness` bajo de 3 niveles a 2: `online`/`stale`, corte a 3600s, tal como se pidio).
- **Buscador de dispositivos**: el selector de vehiculo del toolbar era un `<select>` nativo (no se puede escribir para filtrar). Se reemplazo por un `<input>` con `<datalist>` (autocompletado nativo) que ademas filtra en vivo la lista lateral de "Vehiculos" mientras se escribe, y funciona para carros y drones (buscar "dron" filtra por tipo).
- **Seleccionar un vehiculo/dron carga su recorrido automaticamente** (antes solo centraba el mapa y habia que apretar "Recorrido" aparte). Aplica al hacer click en la lista lateral, en el marcador del mapa, o al escribir el nombre exacto en el buscador.

**Otras pantallas** (resumen de la revision anterior, ver conversacion/commits para detalle):
- Administracion de dispositivos: **cerrado en paridad visual basica**. Incluye CRUD de camaras, RBox, vehiculos y drones, KPI cards de cabecera y etiquetas por dispositivo para Video activo, Reconocimiento, Telemetria OK, RBox, alertas y estado activo/inactivo, sin cambiar contratos de API.
- Centro de camaras: **cerrado** — la lista ahora muestra miniatura real (mismo endpoint de snapshot) por camara online; las offline quedan con un placeholder solido en vez de intentar cargar video. El switch global Normal/Inferencia se retiro y la alternancia quedo sobre el visor como en el legacy. Los eventos recientes ya son interactivos: click/Enter/Espacio abre una ventana flotante con imagen o video y metadata usando el mismo proxy `/api/v1/events/media/...` de la pantalla de eventos.
- Roles y ventanas visibles: **cerrado** para navegacion y rutas HTML. `master/admin` ven administracion, notificaciones y servicios; `viewer` ve dashboard/camaras/mapa/eventos/vehiculos/reportes/perfil; `operator_cameras` cae en camaras y no ve mapa/admin; `operator_map` cae en mapa y no ve camaras/admin. Las APIs mantienen sus permisos existentes.
- Reportes: **cerrado en flujo operativo legacy principal**. Los filtros ahora cambian segun la pestana activa para no mostrar Cedula/Mes/Brecha cuando no aplican. Click/Enter/Espacio en una fila diaria abre el reporte individual de esa cedula; click/Enter/Espacio en el resumen individual filtra sesiones por dia. Se mantienen las exportaciones CSV existentes.
- Gestion de kilometros: **cerrado en paridad practica diaria**. Se agrego filtro por tipo de automovil, botones rapidos Hoy/Ayer y exportacion CSV client-side del reporte diario cargado. El PDF y envio programado siguen usando los endpoints Django existentes.
- Notificaciones: **cerrado en flujo operativo principal**. Se agrego resumen de correos, chats, SMTP y Telegram; los campos de alta rapida aceptan Enter; y los contadores se actualizan al agregar/quitar destinatarios sin recargar la pagina.
- Perfil: **cerrado en flujo principal**. Recupera la seccion de accion rapida del legacy con enlaces filtrados por rol para no ofrecer ventanas no permitidas.
- Usuarios: **cerrado en flujo operativo principal**. Se agrego busqueda por usuario/correo/organizacion/rol, filtro por organizacion y chips de rol/estado en usuarios y organizaciones, conservando las restricciones master/admin ya implementadas en backend.
- Eventos: **cerrado en flujo operativo principal**. Las tarjetas ya son accesibles por teclado, conservan ventana flotante de detalle y se agrego accion Limpiar filtros para volver rapidamente al historial completo.
- Pendiente antes del corte definitivo: prueba visual/manual con usuario real, datos reales de eventos/evidencia y confirmacion de los flujos de creacion/edicion/eliminacion en produccion.

### Infraestructura agregada en esta sesion

- `https://beta.robio-ai.com` -> Nginx con certificado Let's Encrypt propio -> `127.0.0.1:8020` (gunicorn), sirviendo `/static/` directo desde `staticfiles/`. Requirio agregar `beta.robio-ai.com` a `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` en `.env`.
- `127.0.0.1:8021` (Nginx local, sin dominio): mismo patron, para pruebas rapidas sin depender de DNS/HTTPS. No es para produccion.
- El dominio publico principal `robio-ai.com` queda servido por la plataforma Django (`:8020`).
