from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_base_url: str = Field(default="http://127.0.0.1:8003", alias="API_BASE_URL")
    browser_api_base_url: str = Field(default="/api", alias="BROWSER_API_BASE_URL")
    mediamtx_webrtc_base_url: str = Field(
        default="http://207.246.68.223:8889", alias="MEDIAMTX_WEBRTC_BASE_URL"
    )
    mediamtx_api_url: str = Field(default="http://127.0.0.1:9997", alias="MEDIAMTX_API_URL")
    mediamtx_api_port: int = Field(default=9997, alias="MEDIAMTX_API_PORT")
    public_host: str = Field(default="207.246.68.223", alias="PUBLIC_HOST")
    mediamtx_rtmp_port: int = Field(default=1935, alias="MEDIAMTX_RTMP_PORT")
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8010, alias="DASHBOARD_PORT")
    preview_mode: bool = Field(default=False, alias="PREVIEW_MODE")
    database_url: str = Field(
        default="postgresql://robiotec_app:Robiotec%402026@127.0.0.1:5432/robiotec_vms",
        alias="DATABASE_URL",
    )
    ssh_events_host: str = Field(default="100.93.62.24", alias="SSH_EVENTS_HOST")
    ssh_events_user: str = Field(default="robiotec", alias="SSH_EVENTS_USER")
    ssh_events_password: str = Field(default="123456", alias="SSH_EVENTS_PASSWORD")
    ssh_events_port: int = Field(default=22, alias="SSH_EVENTS_PORT")
    ssh_events_base_path: str = Field(
        default="/home/robiotec/Documents/VICTOR/Object_Recognition/src/unified/results_presentacion",
        alias="SSH_EVENTS_BASE_PATH",
    )
    # Ruta a clave privada SSH. Si se define, se usa en lugar de contraseña.
    ssh_key_path: str = Field(default="", alias="SSH_KEY_PATH")
    # Ruta a fichero known_hosts. Si existe, se activa RejectPolicy en lugar de AutoAddPolicy.
    ssh_known_hosts_path: str = Field(default="", alias="SSH_KNOWN_HOSTS_PATH")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_cache_ttl_seconds: int = Field(default=300, alias="TELEGRAM_BOT_CACHE_TTL_SECONDS")
    telegram_ffmpeg_threads: int = Field(default=1, alias="TELEGRAM_FFMPEG_THREADS")
    telegram_max_event_age_seconds: int = Field(default=3600, alias="TELEGRAM_MAX_EVENT_AGE_SECONDS")
    plate_lookup_api_url: str = Field(default="", alias="PLATE_LOOKUP_API_URL")
    plate_lookup_api_token: str = Field(default="", alias="PLATE_LOOKUP_API_TOKEN")
    plate_lookup_timeout_seconds: float = Field(default=2.5, alias="PLATE_LOOKUP_TIMEOUT_SECONDS")
    plate_lookup_cache_ttl_seconds: int = Field(default=300, alias="PLATE_LOOKUP_CACHE_TTL_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
