from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SAR Backend"
    env: str = "dev"

    api_prefix: str = "/api/v1"

    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    database_url: str = "postgresql+psycopg://sar:sar@db:5432/sar"
    redis_url: str = "redis://redis:6379/0"
    task_execution_mode: str = "celery"  # celery | inline

    s3_endpoint_url: str = "http://minio:9000"
    # Optional public endpoint used only for presigned URL generation.
    # Keep s3_endpoint_url as internal service URL for backend read/write.
    s3_presign_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "sar"
    storage_backend: str = "s3"  # s3 | local
    local_storage_dir: str = "./data/storage"
    local_data_dir: str = "./data"

    default_project_name: str = "default"

    upload_tmp_dir: str = "/data/uploads"
    max_upload_part_bytes: int = 8 * 1024 * 1024

    task_time_limit_seconds: int = 300
    task_max_retries: int = 3
    thumbnail_levels: str = "2048,1024,512,256"
    thumbnail_quality: int = 80

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    metrics_path: str = "/metrics"
    frontend_dist_dir: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
