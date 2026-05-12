from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import Role, User, UserRole

DEFAULT_ROLES = ["master", "company_admin", "area_admin", "operator", "viewer"]


def get_user_roles(db: Session, user: User) -> list[str]:
    rows = db.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    )
    return [row[0] for row in rows]


def authenticate_user(db: Session, username: str, password: str) -> tuple[User, list[str]] | None:
    user = db.scalar(select(User).where(User.username == username, User.active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        return None
    return user, get_user_roles(db, user)


def create_jwt_for_user(db: Session, user: User) -> str:
    return create_access_token(user.id, user.username, get_user_roles(db, user))


def ensure_default_roles(db: Session) -> None:
    existing = set(db.scalars(select(Role.name)).all())
    for role_name in DEFAULT_ROLES:
        if role_name not in existing:
            db.add(Role(name=role_name))
    db.commit()


def ensure_master_user(db: Session, username: str, password: str) -> None:
    ensure_default_roles(db)
    user = db.scalar(select(User).where(User.username == username))
    master_role = db.scalar(select(Role).where(Role.name == "master"))
    if user:
        changed = False
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            changed = True
        if not user.active:
            user.active = True
            changed = True
        has_master_role = db.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == master_role.id)
        )
        if not has_master_role:
            db.add(UserRole(user_id=user.id, role_id=master_role.id))
            changed = True
        if changed:
            db.commit()
        return
    user = User(username=username, password_hash=hash_password(password), active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=master_role.id))
    db.commit()
