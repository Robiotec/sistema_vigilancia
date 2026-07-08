"""Production settings for systemd/Gunicorn."""

from .base import env_bool
from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
