from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    public_url: str = "https://nbro.ithute.co.ls"
    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_audience: str = "nbros"
    auth_jwks_url: str = "https://auth.ithute.co.ls/.well-known/jwks.json"
    bootstrap_admin_email: str = "justy@ithute.co.ls"

    model_config = SettingsConfigDict(env_prefix="NBROS_", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
