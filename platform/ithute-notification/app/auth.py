from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from .config import Settings, get_settings


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class ServicePrincipal:
    client_id: str
    scopes: frozenset[str]


class AuthVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.auth_jwks_url, cache_keys=True)

    def service(self, token: str, required_scope: str) -> ServicePrincipal:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.auth_issuer.rstrip("/"),
                audience="ithute-notification",
                leeway=max(0, self.settings.auth_clock_skew_seconds),
                options={
                    "require": [
                        "iss", "sub", "azp", "aud", "scope", "token_use",
                        "service_auth", "jti", "iat", "nbf", "exp",
                    ]
                },
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise AuthError("invalid Ithute managed service token") from exc

        if claims.get("token_use") != "service" or claims.get("service_auth") != "managed":
            raise AuthError("managed Ithute service token required")
        client_id = claims.get("azp")
        if not isinstance(client_id, str) or not client_id or claims.get("sub") != f"service:{client_id}":
            raise AuthError("service identity claims are inconsistent")
        scopes = frozenset(value for value in str(claims.get("scope") or "").split() if value)
        if required_scope not in scopes:
            raise AuthError(f"{required_scope} scope required")
        if int(claims["exp"]) - int(claims["iat"]) > self.settings.auth_max_service_token_seconds:
            raise AuthError("service token lifetime exceeds policy")
        return ServicePrincipal(client_id=client_id, scopes=scopes)


@lru_cache
def verifier() -> AuthVerifier:
    return AuthVerifier(get_settings())
