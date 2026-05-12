from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.auth import StreamTokenResponse
from app.schemas.stream import StreamStatusResponse
from app.services.stream_service import (
    build_viewer_url,
    can_user_read,
    create_read_token,
    get_stream_by_path,
    mediamtx_path_is_online,
)

router = APIRouter(tags=["streams"])


@router.get("/streams/{path:path}/status", response_model=StreamStatusResponse)
async def stream_status(
    path: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamStatusResponse:
    stream_path = get_stream_by_path(db, path)
    if not stream_path or not can_user_read(db, current_user, stream_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Stream no autorizado")
    if not await mediamtx_path_is_online(path):
        return StreamStatusResponse(online=False, message="Video no disponible")
    return StreamStatusResponse(online=True, message="Video disponible", viewer_url=build_viewer_url(path))


@router.post("/stream/token/{path:path}", response_model=StreamTokenResponse)
def create_stream_token(
    path: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamTokenResponse:
    stream_path = get_stream_by_path(db, path)
    if not stream_path or not can_user_read(db, current_user, stream_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Stream no autorizado")
    token = create_read_token(db, current_user, stream_path)
    return StreamTokenResponse(
        token=token,
        expires_in=get_settings().opaque_token_expire_seconds,
        viewer_url=build_viewer_url(path, token),
    )

