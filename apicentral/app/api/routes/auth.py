from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserMe
from app.services.auth_service import authenticate_user, create_jwt_for_user, get_user_roles

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    result = authenticate_user(db, payload.username, payload.password)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
    user, _roles = result
    return TokenResponse(access_token=create_jwt_for_user(db, user))


@router.get("/me", response_model=UserMe)
def me(current_user=Depends(get_current_user), db: Session = Depends(get_db)) -> UserMe:
    return UserMe(
        id=current_user.id,
        username=current_user.username,
        name=current_user.name,
        email=current_user.email,
        company_id=current_user.company_id,
        active=current_user.active,
        roles=get_user_roles(db, current_user),
    )


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.put("/me")
def update_me(
    payload: UpdateProfileRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Se requiere la contraseña actual")
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
        current_user.password_hash = hash_password(payload.new_password)
    if payload.name is not None:
        current_user.name = payload.name
    if payload.email is not None:
        current_user.email = payload.email
    db.commit()
    db.refresh(current_user)
    return UserMe(
        id=current_user.id,
        username=current_user.username,
        name=current_user.name,
        email=current_user.email,
        company_id=current_user.company_id,
        active=current_user.active,
        roles=get_user_roles(db, current_user),
    )

