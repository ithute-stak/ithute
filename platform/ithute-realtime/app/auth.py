from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from .config import Settings


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class UserPrincipal:
    sub: str
    client_id: str


@dataclass(frozen=True)
class ServicePrincipal:
    client_id: str
    scopes: frozenset[str]


class AuthVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.auth_jwks_url, cache_keys=True)

    def _decode(self, token: str) -> dict[str, Any]:
        signing_key = self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self.settings.auth_issuer.rstrip("/"),
            options={"verify_aud": False},
        )

    @staticmethod
    def _audience(claims: dict[str, Any]) -> str:
        aud = claims.get("aud")
        if isinstance(aud, str):
            return aud
        if isinstance(aud, list) and len(aud) == 1 and isinstance(aud[0], str):
            return aud[0]
        raise AuthError("token must contain one audience")

    def user(self, token: str) -> UserPrincipal:
        try:
            claims = self._decode(token)
        except jwt.PyJWTError as exc:
            raise AuthError("invalid central auth token") from exc
        if claims.get("token_use") != "access":
            raise AuthError("user access token required")
        client_id = self._audience(claims)
        if client_id not in self.settings.user_clients:
            raise AuthError("unapproved product audience")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise AuthError("missing subject")
        return UserPrincipal(sub=sub, client_id=client_id)

    def service(self, token: str, required_scope: str) -> ServicePrincipal:
        try:
            claims = self._decode(token)
        except jwt.PyJWTError as exc:
            raise AuthError("invalid central service token") from exc
        if claims.get("token_use") != "service":
            raise AuthError("service token required")
        if self._audience(claims) != "ithute-realtime":
            raise AuthError("wrong service audience")
        scopes = frozenset(str(claims.get("scope", "")).split())
        if required_scope not in scopes:
            raise AuthError(f"{required_scope} scope required")
        client_id = claims.get("azp")
        if not isinstance(client_id, str) or client_id not in self.settings.service_clients:
            raise AuthError("unapproved service client")
        return ServicePrincipal(client_id=client_id, scopes=scopes)
