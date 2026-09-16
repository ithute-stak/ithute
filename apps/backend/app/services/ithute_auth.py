from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
from pydantic_settings import BaseSettings, SettingsConfigDict


class IthuteAuthDisabled(RuntimeError):
    """Raised when central authentication is not enabled for Mailbox DNS."""


class IthuteAuthUnavailable(RuntimeError):
    """Raised when the central signing-key endpoint cannot be reached."""


class IthuteAuthSettings(BaseSettings):
    enabled: bool = False
    issuer: str = "https://auth.ithute.co.ls"
    audience: str = "mailbox-dns"
    jwks_url: str | None = None
    internal_url: str = "http://ithute-auth:8080"

    model_config = SettingsConfigDict(env_prefix="ITHUTE_AUTH_", case_sensitive=False, extra="ignore")

    @property
    def resolved_issuer(self) -> str:
        return self.issuer.rstrip("/")

    @property
    def resolved_jwks_url(self) -> str:
        return self.jwks_url or f"{self.resolved_issuer}/.well-known/jwks.json"

    @property
    def resolved_internal_url(self) -> str:
        return self.internal_url.rstrip("/")


@lru_cache(maxsize=1)
def get_ithute_auth_settings() -> IthuteAuthSettings:
    return IthuteAuthSettings()


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def ithute_auth_enabled() -> bool:
    return bool(get_ithute_auth_settings().enabled)


def _signing_key(token: str, settings: IthuteAuthSettings, jwks_client: Any | None = None):
    client = jwks_client or _jwks_client(settings.resolved_jwks_url)
    try:
        return client.get_signing_key_from_jwt(token).key
    except PyJWKClientConnectionError as error:
        raise IthuteAuthUnavailable("!thute Auth signing keys are unavailable") from error
    except PyJWKClientError as error:
        raise jwt.InvalidTokenError("unknown or invalid !thute Auth signing key") from error


def decode_ithute_access_token(
    token: str,
    *,
    config: IthuteAuthSettings | None = None,
    jwks_client: Any | None = None,
) -> dict[str, Any]:
    """Validate a first-party Ithute Auth human access token."""
    settings = config or get_ithute_auth_settings()
    if not settings.enabled:
        raise IthuteAuthDisabled("!thute Auth is disabled for Mailbox DNS")

    claims = jwt.decode(
        token,
        _signing_key(token, settings, jwks_client),
        algorithms=["RS256"],
        issuer=settings.resolved_issuer,
        audience=settings.audience,
        options={"require": ["iss", "sub", "aud", "sid", "iat", "nbf", "exp", "token_use"]},
    )
    if claims.get("token_use") != "access":
        raise jwt.InvalidTokenError("wrong !thute Auth token type")
    try:
        UUID(str(claims["sub"]))
        UUID(str(claims["sid"]))
    except (KeyError, TypeError, ValueError) as error:
        raise jwt.InvalidTokenError("invalid !thute Auth identity claims") from error
    return claims


def decode_ithute_service_token(
    token: str,
    *,
    audience: str,
    required_scope: str | None = None,
    config: IthuteAuthSettings | None = None,
    jwks_client: Any | None = None,
) -> dict[str, Any]:
    """Validate a short-lived database-managed machine token issued by Ithute Auth."""
    settings = config or get_ithute_auth_settings()
    if not settings.enabled:
        raise IthuteAuthDisabled("!thute Auth is disabled for Mailbox DNS")
    claims = jwt.decode(
        token,
        _signing_key(token, settings, jwks_client),
        algorithms=["RS256"],
        issuer=settings.resolved_issuer,
        audience=audience,
        options={"require": ["iss", "sub", "azp", "aud", "iat", "nbf", "exp", "token_use", "scope", "managed_service_client"]},
    )
    if claims.get("token_use") != "service" or claims.get("managed_service_client") is not True:
        raise jwt.InvalidTokenError("managed Ithute service token required")
    client_id = str(claims.get("azp") or "").strip()
    subject = str(claims.get("sub") or "").strip()
    if not client_id or len(client_id) > 120 or subject != f"service:{client_id}":
        raise jwt.InvalidTokenError("invalid service client identity")
    scopes = {item for item in str(claims.get("scope") or "").split() if item}
    if required_scope and required_scope not in scopes:
        raise jwt.InvalidTokenError("required service scope is missing")
    return claims
