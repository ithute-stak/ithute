from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device, ExternalRiskSignal, User, utcnow
from .security_service import client_ip


DEVICE_HEADER = "x-ithute-device-key"


def user_agent_hash(request: Request) -> str | None:
    value = (request.headers.get("user-agent") or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def requested_device_key(request: Request) -> str | None:
    value = (request.headers.get(DEVICE_HEADER) or "").strip()
    return value[:200] if len(value) >= 8 else None


def resolve_device(db: Session, *, user: User, request: Request) -> Device | None:
    key = requested_device_key(request)
    if not key:
        return None
    device = db.scalar(select(Device).where(Device.user_id == user.id, Device.device_key == key))
    if device is None or not device.is_active or device.revoked_at is not None:
        return None
    device.last_seen_at = utcnow()
    device.last_seen_ip = client_ip(request)
    ua_hash = user_agent_hash(request)
    if ua_hash:
        device.user_agent_hash = device.user_agent_hash or ua_hash
    return device


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    reasons: tuple[str, ...]

    @property
    def level(self) -> str:
        if self.score >= 70:
            return "high"
        if self.score >= 35:
            return "medium"
        return "low"

    def reasons_json(self) -> str:
        return json.dumps(list(self.reasons), separators=(",", ":"), sort_keys=True)


def assess_login_risk(
    *,
    db: Session,
    user: User,
    request: Request,
    device: Device | None,
    auth_method: str,
) -> RiskAssessment:
    score = 0
    reasons: list[str] = []
    ip = client_ip(request)

    if user.last_login_ip and ip and user.last_login_ip != ip:
        score += 25
        reasons.append("new_ip")

    if device is None:
        score += 20
        reasons.append("unrecognized_device")
    elif device.trusted_at is None:
        score += 15
        reasons.append("untrusted_device")

    if auth_method != "passkey":
        score += 15
        reasons.append("password_auth")

    if user.is_platform_admin and auth_method != "passkey":
        score += 50
        reasons.append("privileged_without_passkey")

    active_external = db.scalars(
        select(ExternalRiskSignal).where(
            ExternalRiskSignal.user_id == user.id,
            ExternalRiskSignal.verified.is_(True),
            ExternalRiskSignal.expires_at > utcnow(),
        )
    ).all()
    if active_external:
        # Multiple reports from the same campaign must not make risk unbounded.
        # The central service owns the weights and caps total external influence.
        external_weight = min(40, max(int(row.risk_weight) for row in active_external))
        score += external_weight
        signal_types = {row.signal_type for row in active_external}
        if "mail.bec.verified" in signal_types:
            reasons.append("recent_verified_bec_exposure")
        if "mail.phishing.verified" in signal_types:
            reasons.append("recent_verified_phishing_exposure")

    return RiskAssessment(min(score, 100), tuple(dict.fromkeys(reasons)))


def initialize_device(
    db: Session,
    *,
    user: User,
    device_key: str,
    platform: str,
    label: str | None,
    request: Request,
) -> Device:
    device = db.scalar(select(Device).where(Device.user_id == user.id, Device.device_key == device_key))
    ip = client_ip(request)
    ua_hash = user_agent_hash(request)
    if device is None:
        device = Device(
            user_id=user.id,
            device_key=device_key,
            platform=platform,
            label=label,
            first_seen_ip=ip,
            last_seen_ip=ip,
            user_agent_hash=ua_hash,
        )
        db.add(device)
    else:
        device.platform = platform
        device.label = label
        device.is_active = True
        device.revoked_at = None
        device.last_seen_at = utcnow()
        device.last_seen_ip = ip
        if ua_hash:
            device.user_agent_hash = ua_hash
    return device
