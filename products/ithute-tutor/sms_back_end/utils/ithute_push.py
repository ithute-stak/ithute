from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from database.config.config import settings


_service_token: str | None = None
_service_token_expires_at: float = 0.0


def _get_service_token() -> str:
    global _service_token, _service_token_expires_at

    if _service_token and time.monotonic() < _service_token_expires_at - 15:
        return _service_token

    if not settings.PUSH_SERVICE_CLIENT_SECRET:
        raise RuntimeError("PUSH_SERVICE_CLIENT_SECRET is not configured")

    response = httpx.post(
        settings.auth_service_token_url,
        json={
            "client_id": settings.PUSH_SERVICE_CLIENT_ID,
            "client_secret": settings.PUSH_SERVICE_CLIENT_SECRET,
            "audience": "ithute-push",
            "scope": "push.send",
        },
        timeout=settings.PUSH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    token = str(payload["access_token"])
    expires_in = int(payload.get("expires_in", 300))

    _service_token = token
    _service_token_expires_at = time.monotonic() + expires_in
    return token


def publish_notification(
    *,
    recipient_sub: uuid.UUID | str,
    title: str,
    body: str,
    route: str | None = None,
    data: dict[str, Any] | None = None,
    ttl_seconds: int = 3600,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Publish through central !thute Push; never call device providers directly."""
    headers = {"Authorization": f"Bearer {_get_service_token()}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    response = httpx.post(
        f"{settings.PUSH_BASE_URL.rstrip('/')}/v1/messages",
        json={
            "recipient_sub": str(recipient_sub),
            "title": title,
            "body": body,
            "route": route,
            "sound": "default",
            "data": data or {},
            "ttl_seconds": ttl_seconds,
        },
        headers=headers,
        timeout=settings.PUSH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()
