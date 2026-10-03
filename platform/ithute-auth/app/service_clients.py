from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .managed_service_models import ManagedServiceClient, ManagedServiceCredential
from .models import utcnow


_CAPABILITY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,119}$")


@dataclass(frozen=True)
class ServiceClientAuthError(Exception):
    status_code: int
    detail: str


def normalize_capabilities(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        value = raw.strip().lower()
        if not value or not _CAPABILITY_RE.fullmatch(value):
            raise ValueError(f"invalid service capability: {raw!r}")
        if value not in result:
            result.append(value)
    if not result:
        raise ValueError("at least one service capability is required")
    return tuple(result)


def normalize_scope(scope: str) -> tuple[str, ...]:
    return normalize_capabilities(tuple(part for part in scope.split(" ") if part.strip()))


def encode_capabilities(values: list[str] | tuple[str, ...]) -> str:
    normalized = normalize_capabilities(values)
    return json.dumps(list(normalized), separators=(",", ":"))


def decode_capabilities(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    result: list[str] = []
    for item in parsed:
        if isinstance(item, str) and _CAPABILITY_RE.fullmatch(item) and item not in result:
            result.append(item)
    return tuple(result)


def new_service_secret() -> str:
    # The secret is only returned at creation/rotation time. Auth stores only
    # the SHA-256 digest; the random value carries enough entropy that an
    # offline brute-force attack against the digest is not practical.
    return "ithute_svc_" + secrets.token_urlsafe(48)


def hash_service_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_service_credential(
    db: Session,
    *,
    client: ManagedServiceClient,
    expires_at: datetime | None = None,
) -> tuple[ManagedServiceCredential, str]:
    if expires_at is None:
        expires_at = utcnow() + timedelta(days=30)
    secret = new_service_secret()
    credential = ManagedServiceCredential(
        service_client_id=client.id,
        secret_hash=hash_service_secret(secret),
        secret_prefix=secret[:18],
        expires_at=expires_at,
    )
    db.add(credential)
    db.flush()
    return credential, secret


def authenticate_managed_service_client(
    db: Session,
    *,
    client: ManagedServiceClient,
    client_secret: str,
    audience: str,
    scope: str,
) -> tuple[ManagedServiceCredential, str]:
    now = utcnow()

    # Authenticate first. Do not expose client state, allowed audiences, or
    # allowed scopes to a caller that cannot prove possession of a live secret.
    if not client.is_active:
        raise ServiceClientAuthError(401, "invalid service credentials")
    if client.expires_at is not None and client.expires_at <= now:
        raise ServiceClientAuthError(401, "invalid service credentials")
    credential = db.scalar(
        select(ManagedServiceCredential).where(
            ManagedServiceCredential.service_client_id == client.id,
            ManagedServiceCredential.secret_hash == hash_service_secret(client_secret),
            ManagedServiceCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise ServiceClientAuthError(401, "invalid service credentials")
    if credential.expires_at is not None and credential.expires_at <= now:
        raise ServiceClientAuthError(401, "invalid service credentials")

    # Authorization is evaluated only after machine authentication succeeds.
    requested_audience = audience.strip().lower()
    if not _CAPABILITY_RE.fullmatch(requested_audience):
        raise ServiceClientAuthError(403, "audience not permitted")
    allowed_audiences = set(decode_capabilities(client.allowed_audiences_json))
    if requested_audience not in allowed_audiences:
        raise ServiceClientAuthError(403, "audience not permitted")

    try:
        requested_scopes = normalize_scope(scope)
    except ValueError as exc:
        raise ServiceClientAuthError(403, "scope not permitted") from exc
    allowed_scopes = set(decode_capabilities(client.allowed_scopes_json))
    if not set(requested_scopes).issubset(allowed_scopes):
        raise ServiceClientAuthError(403, "scope not permitted")

    client.last_used_at = now
    credential.last_used_at = now
    return credential, " ".join(requested_scopes)
