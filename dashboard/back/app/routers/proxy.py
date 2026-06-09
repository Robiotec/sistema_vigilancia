"""Proxy transparente hacia API Central para rutas no manejadas por el dashboard."""
from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Request
from fastapi.responses import Response

from back.app.context import get_token
from back.app.state import settings

router = APIRouter(tags=["proxy"])

_PROXY_SKIP_HEADERS = {"host", "content-length", "connection", "accept-encoding", "cookie"}


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def api_proxy(path: str, request: Request) -> Response:
    upstream_url = urljoin(f"{settings.api_base_url.rstrip('/')}/", path)
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _PROXY_SKIP_HEADERS}
    token = get_token(request)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    upstream_request = UrlRequest(
        upstream_url, data=body if body else None, headers=headers, method=request.method
    )
    try:
        with urlopen(upstream_request, timeout=20) as upstream_response:
            return Response(
                content=upstream_response.read(),
                status_code=upstream_response.status,
                media_type=upstream_response.headers.get_content_type(),
            )
    except HTTPError as exc:
        return Response(
            content=exc.read(),
            status_code=exc.code,
            media_type=exc.headers.get_content_type() if exc.headers else "application/json",
        )
    except URLError:
        return Response(content=b'{"error":"api_no_disponible"}', status_code=503, media_type="application/json")
