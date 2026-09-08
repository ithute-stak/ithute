from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env", extra="ignore")

    environment: str = "development"
    app_timezone: str = "Africa/Maseru"
    public_app_url: str = "http://localhost:3004"
    cors_origins: str = "http://localhost:3004"
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "buildtrack"
    db_user: str = "buildtrack"
    db_password: str = "buildtrack"
    redis_url: str = "redis://redis:6379/0"
    media_root: str = "media"
    rate_limit_per_minute: int = 120

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
