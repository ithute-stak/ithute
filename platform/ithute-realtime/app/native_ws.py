from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time


def issue_realtime_ticket(
    *,
    secret: str,
    application_id: str,
    sub: str,
    device_key: str,
    lifetime_seconds: int = 60,
) -> str:
    if not secret:
        raise ValueError("realtime Go gateway secret is not configured")
    lifetime = max(10, min(int(lifetime_seconds), 120))
    payload = {
        "application_id": application_id,
        "sub": sub,
        "device_key": device_key,
        "nonce": secrets.token_urlsafe(12),
        "exp": int(time.time()) + lifetime,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    left = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    right = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{left}.{right}"
