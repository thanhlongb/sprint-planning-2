from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://sprint:sprint@postgres:5432/sprint_planning"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"


settings = Settings()
