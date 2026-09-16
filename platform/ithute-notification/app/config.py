from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_jwks_url: str = "https://auth.ithute.co.ls/.well-known/jwks.json"
    auth_token_url: str = "http://ithute-auth:8080/v1/auth/service-token"
    auth_client_id: str = "ithute-notification"
    auth_client_secret: str = ""
    auth_clock_skew_seconds: int = 30
    auth_max_service_token_seconds: int = 600

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    sms_webhook_url: str = ""
    sms_webhook_token: str = ""

    push_url: str = "http://ithute-push:8080/v1/platform/messages"
    provider_timeout_seconds: float = 10.0
    worker_poll_seconds: float = 2.0
    max_attempts: int = 5

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
