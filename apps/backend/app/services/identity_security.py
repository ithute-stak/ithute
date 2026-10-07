from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import TrustedDevice, User
from app.services.auth_security import request_client_ip

DEVICE_COOKIE_NAME = "ithute_device_id"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
RECOVERY_CODE_COUNT = 10


def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def normalized_device_hash(raw: str) -> str:
    return hash_token(str(raw or "").strip())


def current_device_token(request: Request) -> str:
    return str(request.cookies.get(DEVICE_COOKIE_NAME) or "").strip()


def resolve_or_create_device(
    db: Session,
    *,
    user: User,
    request: Request,
    raw_device_token: str | None = None,
) -> tuple[TrustedDevice, str, bool]:
    token = str(raw_device_token or current_device_token(request) or "").strip()
    created_token = False
    if not token:
        token = new_device_token()
        created_token = True

    digest = normalized_device_hash(token)
    device = db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user.id,
            TrustedDevice.token_hash == digest,
        )
    )
    now = datetime.now(timezone.utc)
    ip = request_client_ip(request)
    user_agent = request.headers.get("user-agent")

    if device is None or device.revoked_at is not None:
        device = TrustedDevice(
            user_id=user.id,
            token_hash=digest,
            first_user_agent=user_agent,
            first_ip_address=ip,
            last_ip_address=ip,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(device)
        db.flush()
        return device, token, True

    device.last_seen_at = now
    device.last_ip_address = ip
    return device, token, False


def assess_login_risk(
    *,
    device: TrustedDevice,
    request: Request,
    is_new_device: bool,
    mfa_verified: bool,
) -> dict[str, Any]:
    score = 0
    reasons: list[dict[str, Any]] = []
    ip = request_client_ip(request)
    user_agent = str(request.headers.get("user-agent") or "")

    if is_new_device:
        score += 35
        reasons.append({"signal": "new_device", "weight": 35})
    elif device.trusted_at is None:
        score += 12
        reasons.append({"signal": "device_not_explicitly_trusted", "weight": 12})

    if device.first_ip_address and ip and device.first_ip_address != ip:
        score += 12
        reasons.append({
            "signal": "network_changed",
            "weight": 12,
            "first_ip": device.first_ip_address,
            "current_ip": ip,
        })

    if device.first_user_agent and user_agent and device.first_user_agent != user_agent:
        score += 18
        reasons.append({"signal": "client_signature_changed", "weight": 18})

    if mfa_verified:
        score = max(0, score - 15)
        reasons.append({"signal": "mfa_verified", "weight": -15})

    level = "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 25 else "low"
    action = "block" if score >= 85 else "step_up" if score >= 35 else "allow"

    return {
        "score": min(100, score),
        "level": level,
        "recommended_action": action,
        "signals": reasons,
        "new_device": is_new_device,
        "trusted_device": device.trusted_at is not None and device.revoked_at is None,
    }


def generate_recovery_codes() -> list[str]:
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(6).upper()
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}")
    return codes


def normalize_recovery_code(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())
