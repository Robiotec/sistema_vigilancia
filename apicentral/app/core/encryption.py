import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    raw_key = settings.field_encryption_key or settings.jwt_secret_key
    try:
        key = raw_key.encode("utf-8")
        if len(key) == 44:
            return Fernet(key)
    except Exception:
        pass
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("fernet:"):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"fernet:{token}"


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith("fernet:"):
        return value
    try:
        return _fernet().decrypt(value.removeprefix("fernet:").encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
