from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    public_url: str = "https://realtime.ithute.co.ls"

    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_jwks_url: str = "https://auth.ithute.co.ls/.well-known/jwks.json"
    allowed_user_clients: str = "loanhub,rsl-pos,mailbox-dns,ithute-account,ithute-tutor,ithute-pay,nbros"
    allowed_service_clients: str = "loanhub,rsl-pos,mailbox-dns,ithute-account,ithute-tutor,ithute-pay,nbros"
    disabled_clients: str = ""

    auth_service_token_url: str = "http://ithute-auth:8080/v1/auth/service-token"
    platform_client_id: str = "ithute-realtime"
    platform_client_secret: str = ""
    push_url: str = "http://ithute-push:8080"
    push_enabled: bool = True

    websocket_auth_timeout_seconds: int = 10
    websocket_presence_ttl_seconds: int = 90
    websocket_idle_timeout_seconds: int = 120
    websocket_send_timeout_seconds: float = 5.0
    max_connections_per_user: int = 8
    max_connections_per_device: int = 3

    max_message_chars: int = 4000
    max_group_members: int = 500
    max_history_page_size: int = 200
    max_event_recipients: int = 5000
    max_replay_page_size: int = 500

    user_send_rate_limit: int = 120
    user_send_rate_window_seconds: int = 60
    activity_rate_limit: int = 180
    activity_rate_window_seconds: int = 60
    service_publish_rate_limit: int = 1000
    service_publish_rate_window_seconds: int = 60

    event_max_attempts: int = 5
    event_retry_seconds: int = 10
    event_worker_poll_seconds: float = 1.0
    event_retention_days: int = 30
    audit_retention_days: int = 180

    model_config = SettingsConfigDict(env_prefix="REALTIME_", case_sensitive=False)

    @property
    def user_clients(self) -> set[str]:
        return {item.strip() for item in self.allowed_user_clients.split(",") if item.strip()}

    @property
    def service_clients(self) -> set[str]:
        return {item.strip() for item in self.allowed_service_clients.split(",") if item.strip()}

    @property
    def disabled_client_set(self) -> set[str]:
        return {item.strip() for item in self.disabled_clients.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
