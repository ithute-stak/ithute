from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from .config import Settings
from .security import _encode, utcnow


def create_managed_service_token(
    *,
    settings: Settings,
    client_id: str,
    audience: str,
    scope: str,
) -> str:
    """Mint a service token that leaf platform services can distinguish from legacy compatibility tokens."""
    issued_at = utcnow()
    payload: dict[str, Any] = {
        "iss": settings.issuer.rstrip("/"),
        "sub": f"service:{client_id}",
        "aud": audience,
        "azp": client_id,
        "scope": scope,
        "token_use": "service",
        "managed_service_client": True,
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.service_token_minutes)).timestamp()),
    }
    return _encode(settings, payload)
