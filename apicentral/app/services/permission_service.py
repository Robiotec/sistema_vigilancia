from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Camera, Drone, StreamPath, User, UserArea, Vehicle
from app.services.auth_service import get_user_roles


def user_can_access_stream(db: Session, user: User, stream_path: StreamPath) -> bool:
    roles = set(get_user_roles(db, user))
    if "master" in roles:
        return True
    if user.company_id != stream_path.company_id:
        return False
    if "company_admin" in roles:
        return True
    if stream_path.area_id is None:
        return "operator" in roles or "viewer" in roles
    return db.scalar(
        select(
            exists().where(
                UserArea.user_id == user.id,
                UserArea.area_id == stream_path.area_id,
            )
        )
    )


_MODEL_BY_RESOURCE_TYPE = {
    "camera": Camera,
    "vehicle": Vehicle,
    "drone": Drone,
}


def resource_is_active(db: Session, stream_path: StreamPath) -> bool:
    model = _MODEL_BY_RESOURCE_TYPE.get(stream_path.resource_type.value)
    if not model:
        return False
    return db.scalar(
        select(exists().where(model.id == stream_path.resource_id, model.active.is_(True)))
    )
