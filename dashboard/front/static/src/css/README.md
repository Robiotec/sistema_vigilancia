# CSS map

Cada template carga un solo entrypoint CSS con el mismo nombre de la pagina:

- `index.html` -> `index.css`
- `camaras.html` -> `camaras.css`
- `mapa.html` -> `mapa.css`
- `eventos.html` -> `eventos.css`
- `usuarios.html` -> `usuarios.css`
- `notificaciones.html` -> `notificaciones.css`
- `registro_vehiculos.html` -> `registro_vehiculos.css`
- `registros.html` -> `registros.css`
- `reportes.html` -> `reportes.css`
- `perfil.html` -> `perfil.css`
- `login.html` -> `login.css`

Archivos compartidos:

- `common.css`: base visual de paginas autenticadas.
- `admin_common.css`: base compartida para pantallas administrativas.
- `responsive.css`: capa responsive compartida.
- `final_overrides.css`: ajustes finales de layout.

Compatibilidad:

- `web_app.css` queda como entrypoint legacy.
- `style_alarmas.css`, `cameras.css` y `camera.css` son aliases hacia los nuevos entrypoints.
