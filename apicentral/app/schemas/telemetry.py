from uuid import UUID

from pydantic import BaseModel, Field


class DroneTelemetryIn(BaseModel):
    drone_id: UUID | None = None
    payload: dict = Field(default_factory=dict)


class VehicleTelemetryIn(BaseModel):
    vehicle_id: UUID | None = None
    payload: dict = Field(default_factory=dict)

