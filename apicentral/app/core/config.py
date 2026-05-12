from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(alias="JWT_EXPIRE_MINUTES")
    opaque_token_expire_seconds: int = Field(alias="OPAQUE_TOKEN_EXPIRE_SECONDS")
    mediamtx_api_url: str = Field(alias="MEDIAMTX_API_URL")
    mediamtx_webrtc_base_url: str = Field(alias="MEDIAMTX_WEBRTC_BASE_URL")
    public_host: str = Field(default="207.246.68.223", alias="PUBLIC_HOST")
    mediamtx_rtsp_port: int = Field(default=8554, alias="MEDIAMTX_RTSP_PORT")
    mediamtx_rtmp_port: int = Field(default=1935, alias="MEDIAMTX_RTMP_PORT")
    arcom_geojson: str = Field(
        default="/root/robiotec/arcom/arcom_catastro.geojson", alias="ARCOM_GEOJSON"
    )
    osint_geojson: str = Field(
        default="/root/robiotec/osint/osint_layers.geojson", alias="OSINT_GEOJSON"
    )
    osint_report: str = Field(
        default="/root/robiotec/osint/osint_descarga_reporte.json", alias="OSINT_REPORT"
    )
    api_host: str = Field(alias="API_HOST")
    api_port: int = Field(alias="API_PORT")
    master_username: str = Field(alias="MASTER_USERNAME")
    master_password: str = Field(alias="MASTER_PASSWORD")
    field_encryption_key: str | None = Field(default=None, alias="FIELD_ENCRYPTION_KEY")
    cors_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
