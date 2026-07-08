"""Shared Django settings for Robiotec."""

from pathlib import Path

from apps.core.env import database_from_url, env, env_bool, env_list, load_env_file

BASE_DIR = Path(__file__).resolve().parents[2]
load_env_file(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.organizations",
    "apps.accounts",
    "apps.devices",
    "apps.streaming",
    "apps.fleet",
    "apps.geofences",
    "apps.alerts",
    "apps.reports",
    "apps.operations",
    "apps.frontend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.frontend.context_processors.dashboard_assets",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTHENTICATION_BACKENDS = [
    "apps.accounts.authentication.LegacyUserBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

DATABASES = {
    "default": database_from_url(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    )
}

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
ROBIOTEC_SERVE_STATIC_DIRECT = env_bool("ROBIOTEC_SERVE_STATIC_DIRECT", True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.streaming.tasks.*": {"queue": "streaming"},
    "apps.reports.tasks.*": {"queue": "reports"},
    "apps.alerts.tasks.*": {"queue": "alerts"},
    "apps.geofences.tasks.*": {"queue": "fleet"},
}
CELERY_BEAT_SCHEDULE = {
    "check-daily-fleet-report": {
        "task": "apps.reports.tasks.check_daily_fleet_report_schedule",
        "schedule": 300.0,
    },
}

MEDIAMTX_API_URL = env("MEDIAMTX_API_URL", "http://127.0.0.1:9997")
MEDIAMTX_WEBRTC_BASE_URL = env("MEDIAMTX_WEBRTC_BASE_URL", "/mediamtx")
ROBIOTEC_SERVICE_TOKEN = env("ROBIOTEC_SERVICE_TOKEN", "")
ROBIOTEC_FIELD_ENCRYPTION_KEY = env("ROBIOTEC_FIELD_ENCRYPTION_KEY", env("DJANGO_SECRET_KEY", ""))
ROBIOTEC_PUBLIC_HOST = env("ROBIOTEC_PUBLIC_HOST", "127.0.0.1")
MEDIAMTX_RTSP_PORT = int(env("MEDIAMTX_RTSP_PORT", "8554") or "8554")
MEDIAMTX_RTMP_PORT = int(env("MEDIAMTX_RTMP_PORT", "1935") or "1935")
ROBIOTEC_NOTIFICATION_SETTINGS_PATH = env(
    "ROBIOTEC_NOTIFICATION_SETTINGS_PATH",
    str(BASE_DIR / "data" / "notification_settings.json"),
)
ROBIOTEC_MEDIA_PROXY_TIMEOUT_SECONDS = int(env("ROBIOTEC_MEDIA_PROXY_TIMEOUT_SECONDS", "20") or "20")

OSRM_BASE_URL = env("OSRM_BASE_URL", "https://router.project-osrm.org")
OSRM_MATCH_CONFIDENCE_MIN = float(env("OSRM_MATCH_CONFIDENCE_MIN", "0.55") or "0.55")
OSRM_REQUEST_TIMEOUT_SECONDS = float(env("OSRM_REQUEST_TIMEOUT_SECONDS", "0.8") or "0.8")
OSRM_MAX_SEGMENTS_PER_REQUEST = int(env("OSRM_MAX_SEGMENTS_PER_REQUEST", "8") or "8")
OSRM_REQUEST_BUDGET_SECONDS = float(env("OSRM_REQUEST_BUDGET_SECONDS", "6.0") or "6.0")
