# Plan de reemplazo del dashboard actual

Este plan queda como registro historico de la migracion. El dashboard principal es Django en `plataforma/`; el dashboard FastAPI/Jinja legacy ya no atiende el dominio publico ni se habilita en systemd.

## Despliegue actual

- `https://robio-ai.com/` sirve la plataforma Django en `127.0.0.1:8020`.
- `https://beta.robio-ai.com/` tambien sirve la plataforma Django en `127.0.0.1:8020`.
- El servicio `robiotec-dashboard.service` esta retirado; no debe usarse para pantallas ni APIs de dashboard.
- `https://robio-ai.com/mediamtx/` sigue apuntando a MediaMTX.
- La carcasa visual Django ya copia el estilo del dashboard actual: sidebar colapsable, login oscuro, paneles compactos, modales y botones con acento Robiotec.

## Orden recomendado

1. **Administracion de camaras y RBox**
   - Estado: iniciado en Django.
   - Incluye login, permisos por rol, CRUD de camaras/RBox, cifrado RTSP y aprovisionamiento de streams.
   - Falta prueba visual manual de crear/editar/eliminar con usuario real.

2. **Administracion de vehiculos**
   - Estado: iniciado en Django.
   - Incluye registro, edicion, chofer, tipo de automovil, placa, codigo GPS/API, deduplicacion por empresa y soft delete.
   - Reusa `DeviceAdminPage` con la misma lista/modal de Camaras y RBox.
   - Tests agregados para alta, duplicados, edicion preservando codigo y borrado logico.
   - Falta prueba visual manual de crear/editar/eliminar con usuario real.

3. **Administracion de drones**
   - Estado: iniciado en Django.
   - Incluye registro, edicion, proveedor, tipo, modelo, fabricante, serial, estado, publicacion de video y soft delete.
   - Reusa `DeviceAdminPage` con la misma lista/modal de Camaras, RBox y Vehiculos.
   - El alta aprovisiona `stream_paths` y `stream_configs` para publicacion RTMP/MediaMTX.
   - Tests agregados para alta, duplicados, edicion preservando codigo, streams y borrado logico.
   - Falta prueba visual manual de crear/editar/eliminar drones con usuario real.

4. **Mapa y recorridos**
   - Estado: iniciado en Django.
   - Incluye pantalla `/mapa/`, endpoint de ultimas ubicaciones y endpoint de recorrido diario por vehiculo.
   - La linea del recorrido se pinta morada y los puntos se mantienen celestes.
   - El recorrido se segmenta por saltos de tiempo, distancia y velocidad para evitar trazos irreales.
   - Deduplica vehiculos logicos por placa/clave normalizada para no mostrar los 32 registros fuente como si fueran unidades distintas.
   - Incluye capa de geocercas sobre el mapa consumiendo el modulo Django nuevo.
   - Incluye drones en mapa, rutas de drones, iconos por tipo, color por frescura, buscador, basemaps, ARCOM, OSINT y dibujo directo de geocercas.
   - Panel izquierdo actualizado con ficha de unidad, telemetria, camaras asociadas, geocercas internas y concesion minera detectada por lookup ARCOM.
   - Frontend usa `FleetDeviceModel` para tratar carros y drones como dispositivos con capacidades compartidas: telemetria, camaras o ambas.
   - Hibridacion OSRM migrada para vehiculos: Django cachea `vehicle_route_segments`, usa geometria ajustada cuando existe, marca tramos crudos/dudosos y muestra inicio + posicion actual en el frontend.
   - Falta ampliar la misma hibridacion a drones si se decide guardar segmentos historicos de dron.

5. **Centro de camaras en vivo**
   - Estado: iniciado en Django.
   - Incluye pantalla `/camaras/`, API `/api/v1/streaming/camera-viewer/`, selector de camaras, visor MediaMTX/WebRTC, estado online y eventos recientes por camara.
   - Reusa `CameraViewerService` para resolver path, URL de video, estado desde MediaMTX y alcance por organizacion.
   - Visor central actualizado a video en vivo MediaMTX WHEP en grande; snapshots quedan como miniaturas/respaldo.
   - Frontend usa `RealtimeCameraFrame` como artefacto compartido para no duplicar el reproductor.
   - Selector lateral migrado a pills con snapshot, estado, origen y tags de tipo/inferencia como el dashboard viejo.
   - Toolbar de inferencia migrada; guarda `inference_type` por endpoint dedicado `/api/v1/streaming/camera-viewer/<id>/inference/`.
   - Eventos recientes usan tarjetas visuales por tipo (placa/persona/zona/movimiento).
   - Tests agregados para catalogo, eventos y aislamiento por empresa.
   - Falta prueba visual manual con video real embebido y migrar el modo alterno de vista de inferencia/proxy si se confirma que sigue siendo necesario.

6. **Gestion de kilometros y reportes diarios**
   - Estado: iniciado en Django.
   - Incluye reporte PDF diario, tarea Celery programada, activacion/desactivacion y destinatarios por correo.
   - Incluye desglose por geocerca, ingresos, salidas y permanencias.
   - Falta prueba manual con SMTP real antes de dejar el envio automatico encendido.

7. **Alertas y notificaciones**
   - Estado: iniciado en Django.
   - Incluye pantalla `/notificaciones/`, API `/api/v1/alerts/notification-settings/`, destinatarios de correo, chat IDs de Telegram y pruebas manuales de envio.
   - Reusa las tablas legacy `notification_email_recipients`, `notification_telegram_chat_ids` y el JSON actual `notification_settings.json`.
   - Las claves SMTP y token de Telegram se preservan al guardar si el campo viene vacio y no se exponen al frontend.
   - Falta prueba manual con correo/Telegram reales antes de retirar la pantalla legacy.

8. **Eventos de camaras e IA**
   - Estado: iniciado en Django.
   - Incluye pantalla `/eventos/`, API `/api/v1/events/history/`, filtros, paginacion, detalle, proxy de evidencia imagen/video y cambio de estado.
   - Dejar IA como servicio externo; Django solo consume resultados y orquesta permisos.
   - Tests agregados para busqueda, filtros y cambio de estado.
   - Falta validacion manual contra evidencia real almacenada en MinIO/media y comparacion visual con el flujo viejo.

9. **Reportes de detecciones**
   - Estado: iniciado en Django.
   - Incluye pantalla `/reportes/`, KPIs, selector de camaras, reporte de personal diario, individual, sesiones, mensual y estadisticas de placas.
   - API disponible en `/api/v1/reports/detection/...` y exportacion CSV con `format=csv`.
   - Reusa `DetectionReportService` sobre `camera_event_history`, sin depender del router FastAPI legacy.
   - Tests agregados para resumen, sesiones por brecha, mensual, placas y validacion de rangos.
   - Falta prueba visual manual de tablas/exportacion y decidir si se optimizan consultas grandes con SQL PostgreSQL especifico detras del mismo servicio.

10. **Perfil de usuario**
   - Estado: iniciado en Django.
   - Incluye pantalla `/perfil/`, API `/api/v1/auth/profile/`, datos de cuenta, estadisticas por alcance y cambio de contrasena validando la contrasena actual.
   - Reusa usuarios legacy de `users` y sincroniza el usuario interno Django despues de editar nombre/correo.
   - Tests agregados para carga del perfil, conteos por empresa, actualizacion de datos y cambio de contrasena.
   - Falta prueba visual manual con usuario real antes de retirar `perfil.html` legacy.

11. **Usuarios, empresas y permisos**
   - Estado: iniciado en Django.
   - Incluye pantalla `/usuarios/`, API `/api/v1/accounts/access/`, alta/edicion/borrado logico de usuarios legacy y administracion de organizaciones para master.
   - Los roles se mantienen cerrados a los codigos soportados por permisos reales: master, admin, operator_cameras, operator_map y viewer.
   - El rol admin queda limitado a su organizacion y solo puede asignar operadores/visores.
   - Tests agregados para hash de contrasena, alcance por organizacion y bloqueo de empresas a no-master.
   - Falta prueba visual manual con usuario master/admin real y evaluar migracion de areas/perfiles avanzados.

12. **Geocercas**
   - Estado: iniciado en Django.
   - Incluye pantalla `/geocercas/`, API `/api/v1/geofences/overview/`, CRUD de geocercas, alertas recientes y cambio de estado procesado.
   - Mantiene contrato legacy de geocercas `polygon` y `circle`, con color y geometria compatible con el mapa.
   - Admin queda limitado a su organizacion; master puede operar todas las organizaciones.
   - Tests agregados para creacion, alcance por organizacion, borrado logico y alertas procesadas.
   - Falta prueba visual manual con usuario real y dibujo directo desde el mapa.

13. **Servicios externos**
   - Estado: iniciado en Django.
   - Incluye pantalla `/servicios/` y API `/api/v1/operations/overview/` para monitorear procesos systemd, endpoints locales y MediaMTX.
   - Es de solo lectura; no reinicia procesos desde el dashboard.
   - Diferencia servicios criticos de secundarios para que fallas de descargas externas no se confundan con caida total.
   - Tests agregados para resumen de salud y reglas critico/secundario.
   - Mantener RBox, GPS, drones, MediaMTX e IA como procesos independientes.
   - Django debe comunicarse por REST o colas, no importar codigo pesado directamente.
   - Falta prueba visual manual con usuario admin/master real y decidir si se agregan acciones auditadas de reinicio.

## Regla de corte

Un modulo viejo se retira solo cuando:

- La pantalla Django cubre los flujos principales.
- Hay tests automatizados de permisos y reglas criticas.
- El servicio corre en systemd sin errores.
- El usuario valida visualmente el flujo.
- La bitacora registra fecha y resultado.
