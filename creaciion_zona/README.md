# Editor de zonas sobre video

Aplicacion local para reproducir un video MP4, dibujar un poligono sobre la imagen y copiar el resultado como JSON con coordenadas normalizadas y en pixeles.

## Estructura

- `creation_poligono.py`: punto de entrada compatible con el comando original.
- `editor_zona/cli.py`: argumentos de linea de comandos y arranque.
- `editor_zona/server.py`: servidor HTTP, plantilla y entrega de assets/video.
- `editor_zona/templates/index.html`: estructura HTML.
- `editor_zona/static/css/app.css`: estilos de la interfaz.
- `editor_zona/static/js/`: frontend separado por responsabilidad.
- `tests/test_server.py`: pruebas basicas de utilidades del servidor.

## Uso

```bash
python3 creation_poligono.py
```

Tambien puedes indicar otro video o puerto:

```bash
python3 creation_poligono.py --video "/ruta/video.mp4" --port 9000
```

Luego abre:

```text
http://127.0.0.1:8765/
```

## Frontend

Los scripts quedaron divididos asi:

- `dom.js`: referencias al DOM y datos que vienen de la plantilla.
- `utils.js`: funciones pequenas reutilizables.
- `polygon-editor.js`: estado del poligono, render del SVG y exportacion JSON.
- `video-player.js`: controles de reproduccion y tiempo del video.
- `main.js`: cableado general de eventos.

## Verificacion rapida

```bash
python3 -m unittest discover -s tests
python3 -m compileall editor_zona creation_poligono.py
```
