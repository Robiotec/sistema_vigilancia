from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_opaque_token, hash_token, verify_token
from app.models.entities import (
    DevicePublishToken,
    StreamAccessToken,
    StreamPath,
    TokenAction,
    User,
)
from app.services.permission_service import resource_is_active, user_can_access_stream

_mediamtx_client: httpx.AsyncClient | None = None


def _get_mediamtx_client() -> httpx.AsyncClient:
    global _mediamtx_client
    if _mediamtx_client is None or _mediamtx_client.is_closed:
        _mediamtx_client = httpx.AsyncClient(
            timeout=3.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _mediamtx_client


def get_stream_by_path(db: Session, path: str) -> StreamPath | None:
    return db.scalar(select(StreamPath).where(StreamPath.path == path))


def build_viewer_url(path: str, token: str | None = None) -> str:
    base_url = get_settings().mediamtx_webrtc_base_url.rstrip("/")
    url = f"{base_url}/{path.strip('/')}/"
    if token:
        return f"{url}?token={token}"
    return url


async def mediamtx_path_is_online(path: str) -> bool:
    api_url = get_settings().mediamtx_api_url.rstrip("/")
    encoded_path = path.replace("/", "%2F")
    try:
        response = await _get_mediamtx_client().get(f"{api_url}/v3/paths/get/{encoded_path}")
    except httpx.RequestError:
        return False
    if response.status_code != 200:
        return False
    payload = response.json()
    return bool(payload.get("ready") or payload.get("source") or payload.get("readers"))


def create_read_token(db: Session, user: User, stream_path: StreamPath, protocol: str = "whep") -> str:
    settings = get_settings()
    token = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.opaque_token_expire_seconds)
    db.add(
        StreamAccessToken(
            user_id=user.id,
            company_id=stream_path.company_id,
            stream_path_id=stream_path.id,
            token_hash=hash_token(token),
            action=TokenAction.read,
            protocol=protocol,
            expires_at=expires_at,
        )
    )
    db.commit()
    return token


def extract_token(query: str | None, token: str | None, password: str | None) -> str | None:
    if token:
        return token
    if password:
        return password
    if not query:
        return None
    parsed = parse_qs(query)
    values = parsed.get("token")
    return values[0] if values else None


def validate_read_token(db: Session, stream_path: StreamPath, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    now = datetime.now(timezone.utc)
    tokens = db.scalars(
        select(StreamAccessToken).where(
            StreamAccessToken.stream_path_id == stream_path.id,
            StreamAccessToken.action == TokenAction.read,
            StreamAccessToken.revoked.is_(False),
            StreamAccessToken.expires_at > now,
        )
    ).all()
    return any(verify_token(raw_token, item.token_hash) for item in tokens)


def validate_publish_token(db: Session, stream_path: StreamPath, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    now = datetime.now(timezone.utc)
    tokens = db.scalars(
        select(DevicePublishToken).where(
            DevicePublishToken.stream_path_id == stream_path.id,
            DevicePublishToken.active.is_(True),
        )
    ).all()
    for item in tokens:
        if item.expires_at and item.expires_at <= now:
            continue
        if verify_token(raw_token, item.token_hash):
            return True
    return False


def can_publish(db: Session, stream_path: StreamPath, raw_token: str | None) -> bool:
    if not stream_path.active or not stream_path.can_publish:
        return False
    if not resource_is_active(db, stream_path):
        return False
    return validate_publish_token(db, stream_path, raw_token)


def can_user_read(db: Session, user: User, stream_path: StreamPath) -> bool:
    return stream_path.active and resource_is_active(db, stream_path) and user_can_access_stream(db, user, stream_path)
