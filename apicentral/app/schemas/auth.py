from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: UUID
    username: str
    name: str | None = None
    email: str | None = None
    company_id: UUID | None
    active: bool = True
    roles: list[str]


class StreamTokenResponse(BaseModel):
    token: str
    expires_in: int
    viewer_url: str

