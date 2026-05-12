from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
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
        company_id=current_user.company_id,
        roles=get_user_roles(db, current_user),
    )

