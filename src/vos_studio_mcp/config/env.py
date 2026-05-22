"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    mcp_server_name: str = Field(default="vos-studio-mcp", alias="MCP_SERVER_NAME")
    mcp_server_host: str = Field(default="0.0.0.0", alias="MCP_SERVER_HOST")
    mcp_server_port: int = Field(default=8000, alias="MCP_SERVER_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="info", alias="LOG_LEVEL")

    # Database (ADR-0007, ADR-0020)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:54322/postgres",
        alias="DATABASE_URL",
    )

    # Supabase (ADR-0007)
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")

    # Auth — OAuth 2.1 (ADR-0019)
    oauth_issuer_url: str = Field(default="", alias="OAUTH_ISSUER_URL")
    oauth_client_id: str = Field(default="", alias="OAUTH_CLIENT_ID")
    oauth_client_secret: str = Field(default="", alias="OAUTH_CLIENT_SECRET")
    dev_bearer_token: str = Field(default="", alias="DEV_BEARER_TOKEN")

    # Celery + Redis (ADR-0021)
    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND"
    )

    # Asset storage (ADR-0008)
    storage_provider: str = Field(default="r2", alias="STORAGE_PROVIDER")
    storage_endpoint: str = Field(default="", alias="STORAGE_ENDPOINT")
    storage_bucket: str = Field(default="", alias="STORAGE_BUCKET")
    storage_access_key: str = Field(default="", alias="STORAGE_ACCESS_KEY")
    storage_secret_key: str = Field(default="", alias="STORAGE_SECRET_KEY")
    storage_public_base_url: str = Field(default="", alias="STORAGE_PUBLIC_BASE_URL")

    # Provider API keys (ADR-0009, ADR-0016)
    higgsfield_api_key: str = Field(default="", alias="HIGGSFIELD_API_KEY")
    freepik_api_key: str = Field(default="", alias="FREEPIK_API_KEY")
    magnific_api_key: str = Field(default="", alias="MAGNIFIC_API_KEY")

    # Webhook secrets (ADR-0028)
    webhook_secret_higgsfield: str = Field(default="", alias="WEBHOOK_SECRET_HIGGSFIELD")
    webhook_secret_freepik: str = Field(default="", alias="WEBHOOK_SECRET_FREEPIK")
    webhook_secret_magnific: str = Field(default="", alias="WEBHOOK_SECRET_MAGNIFIC")

    # Observability (ADR-0030)
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    sentry_environment: str = Field(default="development", alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(default=0.1, alias="SENTRY_TRACES_SAMPLE_RATE")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for app-wide use."""
    return Settings()
