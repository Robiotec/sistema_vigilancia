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
    public_host: str = Field(default="207.246.68.223", alias="PUBLIC_HOST")
    mediamtx_rtmp_port: int = Field(default=1935, alias="MEDIAMTX_RTMP_PORT")
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8010, alias="DASHBOARD_PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
