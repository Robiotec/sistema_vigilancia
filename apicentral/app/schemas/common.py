from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NamedCreate(BaseModel):
    name: str
    company_id: UUID | None = None
    area_id: UUID | None = None
    active: bool = True


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    active: bool = True


class MessageResponse(BaseModel):
    message: str

