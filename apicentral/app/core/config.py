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
    public_host: str = Field(default="127.0.0.1", alias="PUBLIC_HOST")
    mediamtx_rtsp_port: int = Field(default=8554, alias="MEDIAMTX_RTSP_PORT")
    mediamtx_rtmp_port: int = Field(default=1935, alias="MEDIAMTX_RTMP_PORT")
    service_ingest_token: str = Field(default="", alias="SERVICE_INGEST_TOKEN")
    minio_endpoint: str = Field(default="127.0.0.1:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="eventos", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_public_endpoint: str = Field(default="127.0.0.1:9000", alias="MINIO_PUBLIC_ENDPOINT")
    faces_gallery_dir: str = Field(
        default="/root/robiotec/faces_gallery/data", alias="FACES_GALLERY_DIR"
    )
    faces_gallery_token: str = Field(default="", alias="FACES_GALLERY_TOKEN")
    arcom_geojson: str = Field(
        default="/root/robiotec/arcom/arcom_catastro.geojson", alias="ARCOM_GEOJSON"
    )
    osint_geojson: str = Field(
        default="/root/robiotec/osint/osint_layers.geojson", alias="OSINT_GEOJSON"
    )
    osint_report: str = Field(
        default="/root/robiotec/osint/osint_descarga_reporte.json", alias="OSINT_REPORT"
    )
    osrm_base_url: str = Field(default="https://router.project-osrm.org", alias="OSRM_BASE_URL")
    osrm_match_confidence_min: float = Field(default=0.55, alias="OSRM_MATCH_CONFIDENCE_MIN")
    osrm_request_timeout_seconds: float = Field(default=0.8, alias="OSRM_REQUEST_TIMEOUT_SECONDS")
    osrm_max_segments_per_request: int = Field(default=8, alias="OSRM_MAX_SEGMENTS_PER_REQUEST")
    osrm_request_budget_seconds: float = Field(default=6.0, alias="OSRM_REQUEST_BUDGET_SECONDS")
    api_host: str = Field(alias="API_HOST")
    api_port: int = Field(alias="API_PORT")
    master_username: str = Field(default="robiotec", alias="MASTER_USERNAME")
    master_password: str = Field(alias="MASTER_PASSWORD")
    field_encryption_key: str | None = Field(default=None, alias="FIELD_ENCRYPTION_KEY")
    cors_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
