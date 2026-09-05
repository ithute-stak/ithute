from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tutor owns its own PostgreSQL database. It never reads the central Auth or Push DBs.
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "tutor-db"
    DB_PORT: int = 5432
    DB_USER: str = "ithute_tutor"
    DB_PASSWORD: str = ""
    DB_NAME: str = "ithute_tutor"

    # Public product URLs.
    TUTOR_PUBLIC_URL: str = "https://tutor.ithute.co.ls"
    TUTOR_FRONTEND_URL: str = "https://tutor.ithute.co.ls"

    # Central !thute Auth contract. The public issuer never changes; containers
    # may use AUTH_INTERNAL_BASE_URL/JWKS_URL for private service-to-service traffic.
    AUTH_ISSUER: str = "https://auth.ithute.co.ls"
    AUTH_AUDIENCE: str = "ithute-tutor"
    AUTH_INTERNAL_BASE_URL: Optional[str] = None
    AUTH_JWKS_URL: Optional[str] = None
    AUTH_OIDC_REDIRECT_URI: str = "https://tutor.ithute.co.ls/api/auth/oidc/callback"
    AUTH_ACCESS_COOKIE_NAME: str = "ithute_tutor_access"
    AUTH_REFRESH_COOKIE_NAME: str = "ithute_tutor_refresh"
    AUTH_OIDC_STATE_COOKIE_NAME: str = "ithute_tutor_oidc_state"
    AUTH_OIDC_NONCE_COOKIE_NAME: str = "ithute_tutor_oidc_nonce"
    AUTH_OIDC_VERIFIER_COOKIE_NAME: str = "ithute_tutor_oidc_verifier"
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 30

    # The old Tutor password/JWT stack is migration-only and is disabled by default.
    LEGACY_AUTH_ENABLED: bool = False
    JWT_PRIVATE_KEY: Optional[str] = None
    JWT_PUBLIC_KEY: Optional[str] = None
    JWT_PRIVATE_KEY_PATH: Optional[str] = None
    JWT_PUBLIC_KEY_PATH: Optional[str] = None
    SECRET_KEY: str = ""
    FERNET_SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    RATE_LIMIT: str = "100/minute"
    ALGORITHM: str = "RS256"

    # Central !thute Push. Tutor requests short-lived service tokens from Auth.
    PUSH_BASE_URL: str = "https://push.ithute.co.ls"
    PUSH_SERVICE_CLIENT_ID: str = "ithute-tutor"
    PUSH_SERVICE_CLIENT_SECRET: str = ""
    PUSH_TIMEOUT_SECONDS: float = 10.0

    # Optional M-Pesa integration. Empty values keep the core Tutor API bootable.
    MPESA_API_KEY: str = ""
    MPESA_PUBLIC_KEY: str = ""
    MPESA_BASE_URL: str = ""
    MPESA_MARKET: str = ""
    MPESA_COUNTRY: str = "LS"
    MPESA_CURRENCY: str = "LSL"
    MPESA_SHORTCODE: str = ""
    MPESA_MODEL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url

        return (
            f"postgresql+psycopg2://{self.DB_USER}:"
            f"{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/"
            f"{self.DB_NAME}"
        )

    @property
    def auth_issuer(self) -> str:
        return self.AUTH_ISSUER.rstrip("/")

    @property
    def auth_backend_base_url(self) -> str:
        return (self.AUTH_INTERNAL_BASE_URL or self.auth_issuer).rstrip("/")

    @property
    def auth_jwks_url(self) -> str:
        return self.AUTH_JWKS_URL or f"{self.auth_backend_base_url}/.well-known/jwks.json"

    @property
    def auth_authorization_url(self) -> str:
        # Browser redirects must always use the public issuer hostname.
        return f"{self.auth_issuer}/oauth/authorize"

    @property
    def auth_token_url(self) -> str:
        return f"{self.auth_backend_base_url}/oauth/token"

    @property
    def auth_refresh_url(self) -> str:
        return f"{self.auth_backend_base_url}/v1/auth/refresh"

    @property
    def auth_logout_url(self) -> str:
        return f"{self.auth_backend_base_url}/v1/auth/logout"

    @property
    def auth_service_token_url(self) -> str:
        return f"{self.auth_backend_base_url}/v1/auth/service-token"


settings = Settings()
