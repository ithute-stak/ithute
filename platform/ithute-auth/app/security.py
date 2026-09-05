import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken as FernetInvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from passlib.context import CryptContext

from .config import Settings


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    prefix = "+" if raw.startswith("+") else ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"{prefix}{digits}" if digits else None


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_context.verify(password, encoded)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_authorization_code() -> str:
    return secrets.token_urlsafe(48)


def hash_authorization_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def new_security_token() -> str:
    return secrets.token_urlsafe(48)


def new_numeric_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_security_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_recovery_codes(count: int = 10) -> list[str]:
    return [f"{secrets.token_hex(6)}-{secrets.token_hex(6)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().lower().replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _encode(settings: Settings, payload: dict[str, Any]) -> str:
    return jwt.encode(
        payload,
        settings.private_key,
        algorithm="RS256",
        headers={"kid": settings.jwt_key_id, "typ": "JWT"},
    )


def _verification_key(token: str, settings: Settings) -> Any:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise jwt.InvalidTokenError("missing signing key id")
    if kid == settings.jwt_key_id:
        return settings.public_key
    for jwk in settings.previous_jwks:
        if jwk.get("kid") == kid:
            try:
                return jwt.PyJWK.from_dict(jwk).key
            except (jwt.PyJWKError, ValueError, TypeError) as exc:
                raise jwt.InvalidTokenError("invalid retained signing key") from exc
    raise jwt.InvalidTokenError("unknown signing key")


def create_access_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    client_id: str,
    session_id: uuid.UUID,
    email: str | None,
    phone: str | None,
) -> str:
    issued_at = utcnow()
    payload: dict[str, Any] = {
        "iss": settings.issuer.rstrip("/"),
        "sub": str(user_id),
        "aud": client_id,
        "sid": str(session_id),
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "email": email,
        "phone_number": phone,
        "token_use": "access",
    }
    return _encode(settings, payload)


def create_push_access_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    client_id: str,
    session_id: uuid.UUID,
) -> str:
    """Mint a short-lived Push-only token from a live product session."""
    issued_at = utcnow()
    payload: dict[str, Any] = {
        "iss": settings.issuer.rstrip("/"),
        "sub": str(user_id),
        "aud": "ithute-push",
        "azp": client_id,
        "sid": str(session_id),
        "scope": "push.device",
        "token_use": "push_access",
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.push_user_token_minutes)).timestamp()),
    }
    return _encode(settings, payload)


def create_id_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    client_id: str,
    session_id: uuid.UUID,
    nonce: str,
    email: str | None,
    phone: str | None,
    display_name: str,
    email_verified: bool,
    phone_verified: bool,
) -> str:
    issued_at = utcnow()
    payload: dict[str, Any] = {
        "iss": settings.issuer.rstrip("/"),
        "sub": str(user_id),
        "aud": client_id,
        "sid": str(session_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "nonce": nonce,
        "name": display_name,
        "email": email,
        "email_verified": email_verified,
        "phone_number": phone,
        "phone_number_verified": phone_verified,
        "token_use": "id",
    }
    return _encode(settings, payload)


def create_browser_session_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    security_version: int,
) -> str:
    issued_at = utcnow()
    return _encode(
        settings,
        {
            "iss": settings.issuer.rstrip("/"),
            "sub": str(user_id),
            "aud": "ithute-auth-browser",
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(hours=settings.browser_session_hours)).timestamp()),
            "token_use": "browser_session",
            "sv": security_version,
        },
    )


def decode_browser_session_token(token: str, settings: Settings) -> dict[str, Any]:
    claims = jwt.decode(
        token,
        _verification_key(token, settings),
        algorithms=["RS256"],
        issuer=settings.issuer.rstrip("/"),
        audience="ithute-auth-browser",
        options={"require": ["iss", "sub", "aud", "iat", "nbf", "exp", "token_use", "sv"]},
    )
    if claims.get("token_use") != "browser_session":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def create_service_token(
    *,
    settings: Settings,
    client_id: str,
    audience: str = "ithute-push",
    scope: str = "push.send",
) -> str:
    issued_at = utcnow()
    payload: dict[str, Any] = {
        "iss": settings.issuer.rstrip("/"),
        "sub": f"service:{client_id}",
        "aud": audience,
        "azp": client_id,
        "scope": scope,
        "token_use": "service",
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.service_token_minutes)).timestamp()),
    }
    return _encode(settings, payload)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(
        token,
        _verification_key(token, settings),
        algorithms=["RS256"],
        issuer=settings.issuer.rstrip("/"),
        options={"verify_aud": False},
    )


def _fernet(settings: Settings) -> Fernet:
    if not settings.totp_encryption_key:
        raise RuntimeError("AUTH_TOTP_ENCRYPTION_KEY is required for MFA")
    try:
        return Fernet(settings.totp_encryption_key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("AUTH_TOTP_ENCRYPTION_KEY must be a valid Fernet key") from exc


def new_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(value: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(value.encode("ascii")).decode("ascii")
    except FernetInvalidToken as exc:
        raise RuntimeError("stored MFA secret cannot be decrypted") from exc


def verify_totp(secret: str, code: str) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))


def totp_provisioning_uri(secret: str, *, account_name: str, issuer_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer_name)


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_jwk(settings: Settings) -> dict[str, str]:
    key = serialization.load_pem_public_key(settings.public_key.encode("utf-8"))
    if not isinstance(key, RSAPublicKey):
        raise RuntimeError("!thute Auth requires an RSA public key")
    numbers = key.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": settings.jwt_key_id,
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def public_jwks(settings: Settings) -> list[dict[str, str]]:
    current = public_jwk(settings)
    previous = [item for item in settings.previous_jwks if item.get("kid") != current["kid"]]
    return [current, *previous]
