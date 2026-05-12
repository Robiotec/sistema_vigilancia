from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.stream import MediaMTXAuthRequest
from app.services.permission_service import resource_is_active
from app.services.stream_service import (
    can_publish,
    extract_token,
    get_stream_by_path,
    validate_read_token,
)

router = APIRouter(prefix="/mediamtx", tags=["mediamtx"])


@router.post("/auth", response_model=MessageResponse)
def mediamtx_auth(payload: MediaMTXAuthRequest, db: Session = Depends(get_db)) -> MessageResponse:
    if not payload.path:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Path requerido")
    
    # Publicación libre - cualquier path puede publicar
    if payload.action == "publish":
        return MessageResponse(message="OK")
    
    # Para lectura, verificamos si existe el stream y el token
    stream_path = get_stream_by_path(db, payload.path)
    if not stream_path:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Path no autorizado")

    raw_token = extract_token(payload.query, payload.token, payload.password)
    if (
        payload.action == "read"
        and stream_path.active
        and resource_is_active(db, stream_path)
        and validate_read_token(db, stream_path, raw_token)
    ):
        return MessageResponse(message="OK")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")
