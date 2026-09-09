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

    # Shared Ithute identity. BuildTrack owns product authorization, not passwords.
    auth_issuer: str = "https://auth.ithute.co.ls"
    auth_audience: str = "buildtrack-construction"
    auth_internal_base_url: str = "http://ithute-auth:8080"
    auth_jwks_url: str = "http://ithute-auth:8080/.well-known/jwks.json"
    auth_oidc_redirect_uri: str = "http://localhost:3004/api/v1/access/oidc/callback"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_access_cookie_name: str = "buildtrack_ithute_access"
    auth_refresh_cookie_name: str = "buildtrack_ithute_refresh"
    auth_oidc_state_cookie_name: str = "buildtrack_oidc_state"
    auth_oidc_nonce_cookie_name: str = "buildtrack_oidc_nonce"
    auth_oidc_verifier_cookie_name: str = "buildtrack_oidc_verifier"
    auth_oidc_return_cookie_name: str = "buildtrack_oidc_return"
    auth_cookie_max_age_seconds: int = 60 * 60 * 24 * 30
    legacy_auth_enabled: bool = True
    superadmin_email: str = "justy@ithute.co.ls"
    product_admin_emails: str = "justy@ithute.co.ls,just@ithute.co.ls,supperadmin@ithute.co.ls"

    # Shared Ithute delivery services. Product data remains in BuildTrack.
    push_base_url: str = "http://ithute-push:8080"
    push_service_client_id: str = "buildtrack-construction"
    push_service_client_secret: str = ""
    push_timeout_seconds: float = 10.0
    realtime_base_url: str = "http://ithute-realtime:8080"
    realtime_public_url: str = "https://realtime.ithute.co.ls"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def product_admin_email_list(self) -> list[str]:
        values = [self.superadmin_email, *self.product_admin_emails.split(",")]
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            email = value.strip().lower()
            if email and email not in seen:
                seen.add(email)
                result.append(email)
        return result

    @property
    def auth_authorization_url(self) -> str:
        return f"{self.auth_issuer.rstrip('/')}/oauth/authorize"

    @property
    def auth_token_url(self) -> str:
        return f"{self.auth_internal_base_url.rstrip('/')}/oauth/token"

    @property
    def auth_refresh_url(self) -> str:
        return f"{self.auth_internal_base_url.rstrip('/')}/v1/auth/refresh"

    @property
    def auth_logout_url(self) -> str:
        return f"{self.auth_internal_base_url.rstrip('/')}/v1/auth/logout"

    @property
    def auth_service_token_url(self) -> str:
        return f"{self.auth_internal_base_url.rstrip('/')}/v1/auth/service-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
