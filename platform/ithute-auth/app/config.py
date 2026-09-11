import ipaddress
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    issuer: str = "https://auth.ithute.co.ls"
    access_token_minutes: int = 10
    refresh_token_days: int = 30
    service_token_minutes: int = 5
    push_user_token_minutes: int = 3
    authorization_code_minutes: int = 5
    browser_session_hours: int = 8
    browser_cookie_name: str = "ithute_sso"
    browser_cookie_secure: bool = True
    password_reset_minutes: int = 30
    verification_code_minutes: int = 10
    recovery_rate_window_seconds: int = 3600
    recovery_max_requests_per_ip: int = 20
    recovery_max_requests_per_user: int = 5
    verification_rate_window_seconds: int = 3600
    verification_max_requests_per_user: int = 6
    verification_confirm_rate_window_seconds: int = 900
    verification_confirm_max_failures_per_user: int = 10
    max_login_failures: int = 5
    login_lock_minutes: int = 15
    login_rate_window_seconds: int = 900
    login_rate_max_failures_per_ip: int = 50
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    totp_issuer_name: str = "!thute"
    totp_encryption_key: str = ""
    account_base_url: str = "https://auth.ithute.co.ls"
    webauthn_rp_id: str = "auth.ithute.co.ls"
    webauthn_rp_name: str = "!thute"
    webauthn_origin: str = "https://auth.ithute.co.ls"
    webauthn_challenge_minutes: int = 5
    jwt_private_key_file: str = "/run/secrets/jwt-private.pem"
    jwt_public_key_file: str = "/run/secrets/jwt-public.pem"
    jwt_key_id: str = "ithute-auth-2026-01"
    previous_jwks_json: str = "[]"
    first_party_clients: str = (
        "loanhub:LoanHub,rsl-pos:RSL POS,mailbox-dns:Mailbox DNS,"
        "ithute-account:Ithute Account,ithute-tutor:Ithute Tutor,ithute-pay:Ithute Pay,"
        "nbros:NBros,ithute-realtime:!thute Realtime"
    )
    redirect_uris_json: str = (
        '{"nbros":["https://nbro.ithute.co.ls/api/auth/oidc/callback"]}'
    )
    service_client_secrets_json: str = "{}"
    cors_origins: str = "https://panel.ithute.co.ls,https://nbro.ithute.co.ls"
    push_events_url: str = "http://ithute-push:8080/v1/internal/auth-events"
    push_event_worker_poll_seconds: float = 2.0
    push_event_request_timeout_seconds: float = 5.0
    push_event_lease_seconds: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    sms_webhook_url: str = ""
    sms_webhook_token: str = ""

    # One global human owner is provisioned only inside central !thute Auth.
    # Products receive only the signed is_platform_admin claim and never this
    # password. The production password must be injected at runtime.
    system_owner_email: str = ""
    system_owner_password: str = ""

    model_config = SettingsConfigDict(env_prefix="AUTH_", case_sensitive=False)

    @property
    def private_key(self) -> str:
        return Path(self.jwt_private_key_file).read_text(encoding="utf-8")

    @property
    def public_key(self) -> str:
        return Path(self.jwt_public_key_file).read_text(encoding="utf-8")

    @property
    def client_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.first_party_clients.split(","):
            if not item.strip():
                continue
            client_id, _, name = item.partition(":")
            client_id = client_id.strip()
            if client_id:
                result[client_id] = (name.strip() or client_id)
        # NBros is a repository-owned first-party product. Keep it registered
        # even when an older deployment environment overrides the client list.
        result.setdefault("nbros", "NBros")
        return result

    @property
    def redirect_uris(self) -> dict[str, tuple[str, ...]]:
        parsed = json.loads(self.redirect_uris_json or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("AUTH_REDIRECT_URIS_JSON must be a JSON object")
        result: dict[str, tuple[str, ...]] = {}
        for client_id, values in parsed.items():
            if not isinstance(client_id, str) or not isinstance(values, list):
                continue
            uris: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                uri = value.strip()
                try:
                    parts = urlsplit(uri)
                except ValueError:
                    continue
                if not parts.scheme or not parts.netloc or parts.fragment:
                    continue
                is_https = parts.scheme == "https"
                is_local_http = parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
                if is_https or is_local_http:
                    uris.append(uri)
            if uris:
                result[client_id] = tuple(dict.fromkeys(uris))
        result.setdefault("nbros", ("https://nbro.ithute.co.ls/api/auth/oidc/callback",))
        return result

    @property
    def service_client_secrets(self) -> dict[str, str]:
        parsed = json.loads(self.service_client_secrets_json or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("AUTH_SERVICE_CLIENT_SECRETS_JSON must be a JSON object")
        result: dict[str, str] = {}
        for client_id, secret in parsed.items():
            if isinstance(client_id, str) and isinstance(secret, str) and len(secret) >= 24:
                result[client_id] = secret
        return result

    @property
    def previous_jwks(self) -> list[dict[str, str]]:
        parsed = json.loads(self.previous_jwks_json or "[]")
        if not isinstance(parsed, list):
            raise ValueError("AUTH_PREVIOUS_JWKS_JSON must be a JSON array")
        result: list[dict[str, str]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            required = {"kty", "use", "alg", "kid", "n", "e"}
            if required.issubset(item) and all(isinstance(item[key], str) for key in required):
                result.append({key: str(value) for key, value in item.items() if isinstance(value, str)})
        return result

    @property
    def trusted_proxy_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for value in self.trusted_proxy_cidrs.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue
        return tuple(networks)

    @property
    def allowed_origins(self) -> list[str]:
        origins = [value.strip() for value in self.cors_origins.split(",") if value.strip()]
        if "https://nbro.ithute.co.ls" not in origins:
            origins.append("https://nbro.ithute.co.ls")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
