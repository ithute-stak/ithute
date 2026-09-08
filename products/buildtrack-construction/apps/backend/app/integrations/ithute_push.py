from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()
_service_token: str | None = None
_service_token_expires_at = 0.0


def _service_token_value() -> str:
    global _service_token, _service_token_expires_at
    if _service_token and time.monotonic() < _service_token_expires_at - 15:
        return _service_token
    if not settings.push_service_client_secret:
        raise RuntimeError("BuildTrack Ithute Push service credential is not configured")

    response = httpx.post(
        settings.auth_service_token_url,
        json={
            "client_id": settings.push_service_client_id,
            "client_secret": settings.push_service_client_secret,
            "audience": "ithute-push",
            "scope": "push.send",
        },
        timeout=settings.push_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    _service_token = str(payload["access_token"])
    _service_token_expires_at = time.monotonic() + int(payload.get("expires_in", 300))
    return _service_token


def publish_notification(
    *,
    recipient_sub: str,
    title: str,
    body: str,
    route: str | None = None,
    data: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_service_token_value()}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    response = httpx.post(
        f"{settings.push_base_url.rstrip('/')}/v1/messages",
        json={
            "recipient_sub": recipient_sub,
            "title": title,
            "body": body,
            "route": route,
            "sound": "default",
            "data": data or {},
            "ttl_seconds": 3600,
        },
        headers=headers,
        timeout=settings.push_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()
