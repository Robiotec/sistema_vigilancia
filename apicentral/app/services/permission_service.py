from sqlalchemy import exists, select, text
from sqlalchemy.orm import Session

from app.models.entities import StreamPath, User, UserArea
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


def resource_is_active(db: Session, stream_path: StreamPath) -> bool:
    table_by_type = {
        "camera": "cameras",
        "vehicle": "vehicles",
        "drone": "drones",
    }
    table = table_by_type.get(stream_path.resource_type.value)
    if not table:
        return False
    row = db.execute(text(f"select id from {table} where id = :resource_id and active = true"), {"resource_id": stream_path.resource_id})
    return row.first() is not None
