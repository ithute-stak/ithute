from __future__ import annotations

import re
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
from pydantic_settings import BaseSettings, SettingsConfigDict


_SERVICE_CLIENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,119}$")


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

    model_config = SettingsConfigDict(
        env_prefix="ITHUTE_AUTH_",
        case_sensitive=False,
        extra="ignore",
    )

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
    # Products receive only central Auth public signing keys. They never read
    # the Auth database or private signing key.
    return PyJWKClient(url)


def _signing_key(token: str, settings: IthuteAuthSettings, jwks_client: Any | None = None):
    client = jwks_client or _jwks_client(settings.resolved_jwks_url)
    try:
        return client.get_signing_key_from_jwt(token).key
    except PyJWKClientConnectionError as error:
        raise IthuteAuthUnavailable("!thute Auth signing keys are unavailable") from error
    except PyJWKClientError as error:
        raise jwt.InvalidTokenError("unknown or invalid !thute Auth signing key") from error


def ithute_auth_enabled() -> bool:
    return bool(get_ithute_auth_settings().enabled)


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
        options={
            "require": ["iss", "sub", "aud", "sid", "iat", "nbf", "exp", "token_use"],
        },
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
    config: IthuteAuthSettings | None = None,
    jwks_client: Any | None = None,
) -> dict[str, Any]:
    """Validate a database-managed machine token issued by Ithute Auth.

    Privileged platform APIs deliberately reject legacy environment-secret
    service tokens. New managed tokens carry ``service_auth=managed`` and use
    ``azp`` as the canonical service client identity while ``sub`` remains the
    namespaced JWT subject ``service:<client_id>``.
    """

    settings = config or get_ithute_auth_settings()
    if not settings.enabled:
        raise IthuteAuthDisabled("!thute Auth is disabled for platform services")

    claims = jwt.decode(
        token,
        _signing_key(token, settings, jwks_client),
        algorithms=["RS256"],
        issuer=settings.resolved_issuer,
        audience=audience,
        options={
            "require": [
                "iss",
                "sub",
                "aud",
                "azp",
                "scope",
                "service_auth",
                "jti",
                "iat",
                "nbf",
                "exp",
                "token_use",
            ],
        },
    )
    if claims.get("token_use") != "service" or claims.get("service_auth") != "managed":
        raise jwt.InvalidTokenError("managed Ithute service token required")

    client_id = str(claims.get("azp") or "").strip().lower()
    if not _SERVICE_CLIENT_ID_RE.fullmatch(client_id):
        raise jwt.InvalidTokenError("invalid Ithute service client identity")
    if str(claims.get("sub") or "") != f"service:{client_id}":
        raise jwt.InvalidTokenError("service subject does not match authorized party")

    scope = str(claims.get("scope") or "").strip()
    scopes = tuple(dict.fromkeys(part for part in scope.split() if part))
    if not scopes:
        raise jwt.InvalidTokenError("Ithute service token has no scopes")

    claims["azp"] = client_id
    claims["scope"] = " ".join(scopes)
    return claims
