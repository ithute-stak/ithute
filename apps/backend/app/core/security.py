import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
DKIM_ENVELOPE_PREFIX = "dkim$"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)


def _fernet_from_secret(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _fernet() -> Fernet:
    return _fernet_from_secret(settings.secret_key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt protected secret") from exc


def encrypt_dkim_secret(secret: str) -> str:
    """Encrypt DKIM material with its own key-encryption key.

    Development may fall back to SECRET_KEY so existing local environments keep
    working. Production configuration explicitly requires a distinct
    DKIM_ENCRYPTION_KEY. The envelope carries a key id so later rotation can be
    introduced without changing the DkimKey database schema.
    """
    encryption_key = settings.dkim_encryption_key or settings.secret_key
    ciphertext = _fernet_from_secret(encryption_key).encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"{DKIM_ENVELOPE_PREFIX}{settings.dkim_encryption_key_id}${ciphertext}"


def decrypt_dkim_secret(ciphertext: str) -> str:
    """Decrypt new versioned DKIM envelopes and Phase 8 legacy ciphertext.

    Legacy rows were encrypted directly with SECRET_KEY. Keeping read support
    lets operators rotate/regenerate keys gradually instead of invalidating all
    existing signing material during the Phase 10 upgrade.
    """
    if not ciphertext.startswith(DKIM_ENVELOPE_PREFIX):
        return decrypt_secret(ciphertext)
    try:
        _, key_id, payload = ciphertext.split("$", 2)
    except ValueError as exc:
        raise ValueError("Invalid DKIM encryption envelope") from exc
    if key_id != settings.dkim_encryption_key_id:
        raise ValueError(f"Unsupported DKIM encryption key id: {key_id}")
    encryption_key = settings.dkim_encryption_key or settings.secret_key
    try:
        return _fernet_from_secret(encryption_key).decrypt(payload.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt DKIM signing secret") from exc


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.app_name)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_api_key() -> tuple[str, str, str]:
    raw = "mdns_" + secrets.token_urlsafe(32)
    return raw, raw[:12], hash_token(raw)
