from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    public_url: str = "https://nbro.ithute.co.ls"
    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_audience: str = "nbros"
    auth_jwks_url: str = "https://auth.ithute.co.ls/.well-known/jwks.json"
    auth_service_token_url: str = "https://auth.ithute.co.ls/v1/auth/service-token"
    bootstrap_admin_email: str = "justy@ithute.co.ls"
    upload_dir: str = "/data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024

    realtime_public_url: str = "https://realtime.ithute.co.ls"
    realtime_service_client_secret: str = ""
    realtime_publish_enabled: bool = True

    fleet_monitor_interval_seconds: int = 60
    fleet_monitor_lock_seconds: int = 120

    ai_enabled: bool = False
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_prefix="NBROS_", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
