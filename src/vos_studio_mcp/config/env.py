from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    mcp_server_name: str = "vos-studio-mcp"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000
    debug: bool = False
    log_level: str = "info"

    # Database (ADR-0007, ADR-0020)
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:54322/postgres"

    # Supabase (ADR-0007)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Auth — OAuth 2.1 (ADR-0019)
    oauth_issuer_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    dev_bearer_token: str = ""  # local dev only, never in production

    # Celery + Redis (ADR-0021)
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Asset storage (ADR-0008)
    storage_provider: str = "r2"
    storage_endpoint: str = ""
    storage_bucket: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_public_base_url: str = ""

    # Provider API keys (ADR-0009, ADR-0016)
    higgsfield_api_key: str = ""
    freepik_api_key: str = ""
    magnific_api_key: str = ""

    # Webhook secrets (ADR-0028)
    webhook_secret_higgsfield: str = ""
    webhook_secret_freepik: str = ""

    # Observability (ADR-0030)
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1


settings = Settings()
