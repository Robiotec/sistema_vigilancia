from uuid import UUID

from pydantic import BaseModel


class MediaMTXAuthRequest(BaseModel):
    action: str
    path: str | None = None
    user: str | None = None
    password: str | None = None
    token: str | None = None
    query: str | None = None
    protocol: str | None = None
    ip: str | None = None


class StreamStatusResponse(BaseModel):
    online: bool
    message: str
    viewer_url: str | None = None


class StreamPathCreate(BaseModel):
    company_id: UUID
    area_id: UUID | None = None
    path: str
    resource_type: str
    resource_id: UUID
    active: bool = True
    can_publish: bool = True

