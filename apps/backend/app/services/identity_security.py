from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import redis

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token
from app.models import Mailbox, PhishingFinding, TrustedDevice, User
from app.services.auth_security import request_client_ip

DEVICE_COOKIE_NAME = "ithute_device_id"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
RECOVERY_CODE_COUNT = 10
ADAPTIVE_CHALLENGE_TTL_SECONDS = 600
ADAPTIVE_CHALLENGE_MAX_ATTEMPTS = 5


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

    if device is not None and device.revoked_at is not None:
        token = new_device_token()
        digest = normalized_device_hash(token)
        device = None
        created_token = True

    if device is None:
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



def lookup_device(db: Session, *, user: User, request: Request) -> TrustedDevice | None:
    token = current_device_token(request)
    if not token:
        return None
    device = db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user.id,
            TrustedDevice.token_hash == normalized_device_hash(token),
        )
    )
    if device is None or device.revoked_at is not None:
        return None
    return device


def _adaptive_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _client_binding(request: Request) -> dict[str, str]:
    return {
        "ip": request_client_ip(request),
        "user_agent_hash": hash_token(str(request.headers.get("user-agent") or "")),
    }


def issue_adaptive_challenge(*, user: User, request: Request, risk: dict[str, Any]) -> tuple[str, str, bool]:
    binding = _client_binding(request)
    active_key = f"ithute:adaptive:active:{user.id}:{hash_token(binding['ip'])}:{binding['user_agent_hash']}"
    try:
        client = _adaptive_redis()
        existing = client.get(active_key)
        if existing:
            return str(existing), "", False

        challenge_id = secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        payload = {
            "user_id": str(user.id),
            "code_hash": hash_token(code),
            "ip": binding["ip"],
            "user_agent_hash": binding["user_agent_hash"],
            "attempts": 0,
            "risk_score": int(risk.get("score") or 0),
            "risk_level": str(risk.get("level") or "unknown"),
        }
        key = f"ithute:adaptive:challenge:{challenge_id}"
        pipe = client.pipeline()
        pipe.setex(key, ADAPTIVE_CHALLENGE_TTL_SECONDS, json.dumps(payload, separators=(",", ":")))
        pipe.setex(active_key, ADAPTIVE_CHALLENGE_TTL_SECONDS, challenge_id)
        pipe.execute()
        return challenge_id, code, True
    except redis.RedisError as exc:
        raise RuntimeError("Adaptive authentication challenge service is unavailable") from exc


def cancel_adaptive_challenge(*, user: User, request: Request, challenge_id: str) -> None:
    binding = _client_binding(request)
    active_key = f"ithute:adaptive:active:{user.id}:{hash_token(binding['ip'])}:{binding['user_agent_hash']}"
    try:
        client = _adaptive_redis()
        pipe = client.pipeline()
        pipe.delete(f"ithute:adaptive:challenge:{challenge_id}")
        pipe.delete(active_key)
        pipe.execute()
    except redis.RedisError:
        return


def verify_adaptive_challenge(*, user: User, request: Request, challenge_id: str, code: str) -> bool:
    if not challenge_id or len(challenge_id) > 256:
        return False
    key = f"ithute:adaptive:challenge:{challenge_id}"
    binding = _client_binding(request)
    try:
        client = _adaptive_redis()
        raw = client.get(key)
        if not raw:
            return False
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            client.delete(key)
            return False

        if (
            str(payload.get("user_id") or "") != str(user.id)
            or str(payload.get("ip") or "") != binding["ip"]
            or str(payload.get("user_agent_hash") or "") != binding["user_agent_hash"]
        ):
            return False

        attempts = int(payload.get("attempts") or 0) + 1
        if attempts > ADAPTIVE_CHALLENGE_MAX_ATTEMPTS:
            client.delete(key)
            return False

        if not secrets.compare_digest(str(payload.get("code_hash") or ""), hash_token(str(code or "").strip())):
            payload["attempts"] = attempts
            ttl = client.ttl(key)
            if ttl > 0:
                client.setex(key, ttl, json.dumps(payload, separators=(",", ":")))
            return False

        active_key = f"ithute:adaptive:active:{user.id}:{hash_token(binding['ip'])}:{binding['user_agent_hash']}"
        pipe = client.pipeline()
        pipe.delete(key)
        pipe.delete(active_key)
        pipe.execute()
        return True
    except (redis.RedisError, TypeError, ValueError, json.JSONDecodeError):
        return False


def recent_mail_threat_context(db: Session, *, user: User) -> dict[str, Any]:
    """Return a privacy-minimized identity risk signal from verified mail threats.

    Only immutable, high-confidence human verdicts for the account's own mailbox
    are considered. Raw message bodies, subjects and senders are not returned to
    the authentication engine.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    rows = db.scalars(
        select(PhishingFinding)
        .join(Mailbox, Mailbox.id == PhishingFinding.mailbox_id)
        .where(
            Mailbox.address == str(user.email).strip().lower(),
            PhishingFinding.finding_type == "mail_intelligence_training_label",
            PhishingFinding.resolved.is_(True),
            PhishingFinding.action_taken.in_(["phishing", "bec"]),
            PhishingFinding.created_at >= cutoff,
        )
        .order_by(PhishingFinding.created_at.desc())
        .limit(20)
    ).all()

    trusted = []
    for row in rows:
        metadata = row.metadata_json or {}
        confidence = float(metadata.get("label_confidence") or 0.0)
        label = str(metadata.get("verified_label") or row.action_taken or "").lower()
        if confidence < 0.90 or label not in {"phishing", "bec"}:
            continue
        trusted.append({
            "label": label,
            "confidence": round(confidence, 3),
            "created_at": row.created_at.isoformat(),
        })

    if not trusted:
        return {
            "active": False,
            "weight": 0,
            "signal": None,
            "verified_threat_count": 0,
            "window_hours": 48,
        }

    labels = {item["label"] for item in trusted}
    # Deliberately bounded: confirmed threat exposure should amplify other
    # suspicious login evidence, not lock an account by itself.
    weight = 18 if "bec" in labels else 12
    signal = "recent_verified_bec_exposure" if "bec" in labels else "recent_verified_phishing_exposure"
    return {
        "active": True,
        "weight": weight,
        "signal": signal,
        "verified_threat_count": len(trusted),
        "window_hours": 48,
        "highest_confidence": max(item["confidence"] for item in trusted),
        "labels": sorted(labels),
    }


def assess_login_risk(
    *,
    device: TrustedDevice | None,
    request: Request,
    is_new_device: bool,
    mfa_verified: bool,
    contextual_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    score = 0
    reasons: list[dict[str, Any]] = []
    ip = request_client_ip(request)
    user_agent = str(request.headers.get("user-agent") or "")

    if is_new_device or device is None:
        score += 35
        reasons.append({"signal": "new_device", "weight": 35})
    elif device.trusted_at is None:
        score += 12
        reasons.append({"signal": "device_not_explicitly_trusted", "weight": 12})

    if device is not None and device.first_ip_address and ip and device.first_ip_address != ip:
        score += 12
        reasons.append({
            "signal": "network_changed",
            "weight": 12,
            "first_ip": device.first_ip_address,
            "current_ip": ip,
        })

    if device is not None and device.first_user_agent and user_agent and device.first_user_agent != user_agent:
        score += 18
        reasons.append({"signal": "client_signature_changed", "weight": 18})

    for contextual in contextual_signals or []:
        weight = max(0, min(25, int(contextual.get("weight") or 0)))
        signal = str(contextual.get("signal") or "").strip()
        if not signal or weight <= 0:
            continue
        score += weight
        reasons.append({
            "signal": signal,
            "weight": weight,
            "source": str(contextual.get("source") or "context"),
            "evidence_count": int(contextual.get("evidence_count") or 0),
        })

    if mfa_verified:
        score = max(0, score - 15)
        reasons.append({"signal": "mfa_verified", "weight": -15})

    level = "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 25 else "low"
    action = "block" if score >= 75 else "step_up" if score >= 30 else "allow"

    return {
        "score": min(100, score),
        "level": level,
        "recommended_action": action,
        "signals": reasons,
        "new_device": is_new_device,
        "trusted_device": bool(device is not None and device.trusted_at is not None and device.revoked_at is None),
    }


def generate_recovery_codes() -> list[str]:
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(6).upper()
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}")
    return codes


def normalize_recovery_code(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())
