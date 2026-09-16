from __future__ import annotations

import uuid
from datetime import timedelta

import jwt

from .config import Settings
from .security import utcnow


def create_managed_service_token(
    *,
    settings: Settings,
    client_id: str,
    audience: str,
    scope: str,
) -> str:
    """Mint a service token that downstream platform APIs can distinguish
    from the temporary environment-secret compatibility path.
    """

    issued_at = utcnow()
    payload = {
        "iss": settings.issuer.rstrip("/"),
        "sub": f"service:{client_id}",
        "aud": audience,
        "azp": client_id,
        "scope": scope,
        "token_use": "service",
        "service_auth": "managed",
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.service_token_minutes)).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.private_key,
        algorithm="RS256",
        headers={"kid": settings.jwt_key_id, "typ": "JWT"},
    )
