"""Test settings that do not touch the production PostgreSQL database."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "tests-only-secret"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",  # noqa: F405
    }
}
MEDIA_ROOT = BASE_DIR / "test-media"  # noqa: F405
STATIC_ROOT = BASE_DIR / "test-staticfiles"  # noqa: F405
