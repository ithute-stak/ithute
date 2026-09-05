import time
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
    session_id: str


@dataclass(frozen=True)
class ServicePrincipal:
    client_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class LifecyclePrincipal:
    client_id: str = "ithute-auth"


@dataclass(frozen=True)
class AdminPrincipal:
    sub: str
    client_id: str
    session_id: str


class AuthVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.auth_jwks_url, cache_keys=True)

    def _decode(self, token: str, *, required: list[str]) -> dict[str, Any]:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.auth_issuer.rstrip("/"),
                audience="ithute-push",
                leeway=max(0, self.settings.auth_clock_skew_seconds),
                options={"require": required},
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise AuthError("invalid central Auth token") from exc

        now = int(time.time())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise AuthError("token timestamps are invalid")
        if issued_at > now + max(0, self.settings.auth_clock_skew_seconds):
            raise AuthError("token issued-at time is in the future")
        if expires_at <= issued_at:
            raise AuthError("token lifetime is invalid")
        return claims

    @staticmethod
    def _scope(claims: dict[str, Any]) -> set[str]:
        raw = claims.get("scope")
        if not isinstance(raw, str):
            raise AuthError("token scope is invalid")
        return {value for value in raw.split() if value}

    @staticmethod
    def _require_uuid_claim(claims: dict[str, Any], name: str) -> str:
        import uuid

        value = claims.get(name)
        if not isinstance(value, str) or not value:
            raise AuthError(f"missing {name}")
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise AuthError(f"invalid {name}") from exc
        return value

    def user(self, token: str) -> UserPrincipal:
        claims = self._decode(
            token,
            required=["iss", "sub", "aud", "azp", "sid", "scope", "token_use", "jti", "iat", "nbf", "exp"],
        )
        if claims.get("token_use") != "push_access":
            raise AuthError("Push access token required")
        if "push.device" not in self._scope(claims):
            raise AuthError("push.device scope required")
        client_id = claims.get("azp")
        if not isinstance(client_id, str) or client_id not in self.settings.user_clients:
            raise AuthError("unapproved product client")
        sub = self._require_uuid_claim(claims, "sub")
        sid = self._require_uuid_claim(claims, "sid")
        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti:
            raise AuthError("missing token id")
        if int(claims["exp"]) - int(claims["iat"]) > self.settings.auth_max_push_access_seconds:
            raise AuthError("Push access token lifetime exceeds policy")
        return UserPrincipal(sub=sub, client_id=client_id, session_id=sid)

    def service(self, token: str, required_scope: str = "push.send") -> ServicePrincipal:
        claims = self._decode(
            token,
            required=["iss", "sub", "aud", "azp", "scope", "token_use", "jti", "iat", "nbf", "exp"],
        )
        if claims.get("token_use") != "service":
            raise AuthError("service token required")
        scopes = frozenset(self._scope(claims))
        if required_scope not in scopes:
            raise AuthError(f"{required_scope} scope required")
        client_id = claims.get("azp")
        if not isinstance(client_id, str) or client_id not in self.settings.service_clients:
            raise AuthError("unapproved service client")
        if claims.get("sub") != f"service:{client_id}":
            raise AuthError("service subject does not match authorized party")
        if int(claims["exp"]) - int(claims["iat"]) > self.settings.auth_max_service_token_seconds:
            raise AuthError("service token lifetime exceeds policy")
        return ServicePrincipal(client_id=client_id, scopes=scopes)

    def lifecycle(self, token: str) -> LifecyclePrincipal:
        claims = self._decode(
            token,
            required=["iss", "sub", "aud", "azp", "scope", "token_use", "jti", "iat", "nbf", "exp"],
        )
        if claims.get("token_use") != "service":
            raise AuthError("service token required")
        if claims.get("azp") != "ithute-auth" or claims.get("sub") != "service:ithute-auth":
            raise AuthError("Auth lifecycle principal required")
        if "push.lifecycle" not in self._scope(claims):
            raise AuthError("push.lifecycle scope required")
        if int(claims["exp"]) - int(claims["iat"]) > self.settings.auth_max_service_token_seconds:
            raise AuthError("lifecycle token lifetime exceeds policy")
        return LifecyclePrincipal()

    def admin(self, token: str) -> AdminPrincipal:
        claims = self._decode(
            token,
            required=["iss", "sub", "aud", "azp", "sid", "scope", "token_use", "jti", "iat", "nbf", "exp"],
        )
        if claims.get("token_use") != "push_admin":
            raise AuthError("Push admin token required")
        if "push.admin" not in self._scope(claims):
            raise AuthError("push.admin scope required")
        client_id = claims.get("azp")
        if not isinstance(client_id, str) or client_id not in self.settings.admin_clients:
            raise AuthError("unapproved Push admin client")
        sub = self._require_uuid_claim(claims, "sub")
        sid = self._require_uuid_claim(claims, "sid")
        if int(claims["exp"]) - int(claims["iat"]) > self.settings.auth_max_admin_token_seconds:
            raise AuthError("Push admin token lifetime exceeds policy")
        return AdminPrincipal(sub=sub, client_id=client_id, session_id=sid)
