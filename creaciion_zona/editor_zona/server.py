from __future__ import annotations

import html
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from typing import Final
from urllib.parse import unquote, urlparse

from .config import AppConfig, INDEX_TEMPLATE_PATH, STATIC_DIR


RANGE_RE: Final[re.Pattern[str]] = re.compile(r"bytes=(\d*)-(\d*)")


def render_index_html(video_name: str) -> bytes:
    template_text = INDEX_TEMPLATE_PATH.read_text(encoding="utf-8")
    template = Template(template_text)
    return template.substitute(video_name=html.escape(video_name)).encode("utf-8")


def resolve_static_asset(request_path: str) -> Path | None:
    if not request_path.startswith("/static/"):
        return None

    relative_path = Path(unquote(request_path.removeprefix("/static/")))
    asset_path = (STATIC_DIR / relative_path).resolve()

    try:
        asset_path.relative_to(STATIC_DIR)
    except ValueError:
        return None

    return asset_path


def parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    match = RANGE_RE.fullmatch(range_header.strip())
    if match is None:
        return None

    start_text, end_text = match.groups()

    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            return None
        start = max(file_size - suffix_length, 0)
        end = file_size - 1

    if start > end or end >= file_size:
        return None

    return start, end

# Configuracion de la aplicacion
class VideoPolygonServer(ThreadingHTTPServer):

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        config: AppConfig,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.config = config

# Video con soporte de rangos HTTP
class VideoPolygonHandler(BaseHTTPRequestHandler):

    server: VideoPolygonServer

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_request(send_body=False)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}")

    def _handle_request(self, send_body: bool) -> None:
        request_path = urlparse(self.path).path

        if request_path in {"/", "/index.html"}:
            self._serve_index(send_body=send_body)
            return

        if request_path.startswith("/static/"):
            self._serve_static(request_path=request_path, send_body=send_body)
            return

        if request_path == "/video":
            self._serve_video(send_body=send_body)
            return

        if request_path == "/health":
            self._send_bytes_response(
                status=HTTPStatus.OK,
                body=b"ok",
                content_type="text/plain; charset=utf-8",
                send_body=send_body,
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada")

    def _serve_index(self, send_body: bool) -> None:
        try:
            body = render_index_html(self.server.config.video_name)
        except FileNotFoundError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "No se encontro la plantilla principal.")
            return

        self._send_bytes_response(
            status=HTTPStatus.OK,
            body=body,
            content_type="text/html; charset=utf-8",
            send_body=send_body,
        )

    def _serve_static(self, request_path: str, send_body: bool) -> None:
        asset_path = resolve_static_asset(request_path)
        if asset_path is None or not asset_path.exists() or not asset_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Asset no encontrado")
            return

        content_type, _ = mimetypes.guess_type(asset_path.name)
        self._send_bytes_response(
            status=HTTPStatus.OK,
            body=asset_path.read_bytes(),
            content_type=content_type or "application/octet-stream",
            send_body=send_body,
        )

    def _serve_video(self, send_body: bool) -> None:
        video_path = self.server.config.video_path

        if not video_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, f"No se encontro el video: {video_path.name}")
            return

        file_size = video_path.stat().st_size
        start = 0
        end = file_size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")

        if range_header:
            byte_range = parse_byte_range(range_header, file_size)
            if byte_range is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return

            start, end = byte_range
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        if not send_body:
            return

        with video_path.open("rb") as video_file:
            video_file.seek(start)
            remaining = content_length
            chunk_size = 1024 * 1024

            while remaining > 0:
                chunk = video_file.read(min(chunk_size, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _send_bytes_response(
        self,
        *,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        send_body: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def run_server(config: AppConfig) -> None:
    with VideoPolygonServer((config.host, config.port), VideoPolygonHandler, config) as httpd:
        print("Servidor listo.")
        print(f"Video: {config.video_path}")
        print(f"Abre en tu navegador: http://{config.host}:{config.port}/")
        print("Ctrl+C para detenerlo.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
