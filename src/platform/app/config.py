from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://sprint:sprint@postgres:5432/sprint_planning"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    # AC5: shared bearer token used when an agent declares scheme="bearer".
    # Per-agent token storage is intentionally out of scope for Phase 1.
    a2a_bearer_token: str | None = None
    platform_base_url: str = "http://localhost:8000"
    # Hard-coded Phase-1 join timeout (minutes).
    join_timeout_minutes: int = 15


settings = Settings()
