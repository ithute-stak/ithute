from __future__ import annotations

import json
from datetime import timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

import redis

from app.core.config import settings

PROFILE_TTL_SECONDS = 180 * 24 * 60 * 60
MAX_RECENT_REFS = 100


def _sender(message: dict[str, Any]) -> str:
    addresses = [addr.lower() for _, addr in getaddresses([str(message.get("from") or "")]) if addr]
    return addresses[0] if addresses else ""


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def _reply_domain(message: dict[str, Any]) -> str:
    addresses = [addr.lower() for _, addr in getaddresses([str(message.get("reply_to") or "")]) if addr]
    return _domain(addresses[0]) if addresses else ""


def _message_hour(message: dict[str, Any]) -> int | None:
    value = str(message.get("date") or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).hour)


def _payment_language(message: dict[str, Any]) -> bool:
    text = f"{message.get('subject') or ''}\n{message.get('body_text') or ''}".lower()
    return any(term in text for term in ("bank details", "bank account", "payment", "transfer", "beneficiary", "invoice"))


def empty_profile() -> dict[str, Any]:
    return {
        "observations": 0,
        "hours": {},
        "reply_domains": [],
        "attachment_messages": 0,
        "payment_messages": 0,
        "recent_message_refs": [],
    }


def analyze_behavior(message: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    observations = int(profile.get("observations") or 0)
    hour = _message_hour(message)
    reply_domain = _reply_domain(message)
    known_reply_domains = set(profile.get("reply_domains") or [])
    attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
    payment = _payment_language(message)

    score = 0
    signals: list[dict[str, Any]] = []

    if observations == 0:
        score += 12
        signals.append({"signal": "first_seen_sender", "weight": 12})

    if observations >= 10 and hour is not None:
        hours = profile.get("hours") if isinstance(profile.get("hours"), dict) else {}
        hour_count = int(hours.get(str(hour)) or 0)
        if hour_count / max(1, observations) < 0.05:
            score += 14
            signals.append({"signal": "unusual_sending_hour", "weight": 14, "hour_utc": hour})

    if observations >= 3 and reply_domain and known_reply_domains and reply_domain not in known_reply_domains:
        score += 24
        signals.append({
            "signal": "sender_reply_domain_changed",
            "weight": 24,
            "reply_domain": reply_domain,
            "known_reply_domains": sorted(known_reply_domains)[:8],
        })

    if observations >= 10 and attachments and int(profile.get("attachment_messages") or 0) == 0:
        score += 12
        signals.append({"signal": "unexpected_attachment_pattern", "weight": 12})

    if observations >= 10 and payment and int(profile.get("payment_messages") or 0) == 0:
        score += 22
        signals.append({"signal": "new_payment_request_pattern", "weight": 22})

    if observations >= 20:
        confidence = min(0.98, 0.60 + observations / 200.0)
    elif observations >= 5:
        confidence = 0.55
    else:
        confidence = 0.35

    return {
        "score": min(100, score),
        "state": "high" if score >= 50 else "elevated" if score >= 25 else "watch" if score >= 12 else "stable",
        "confidence": round(confidence, 3),
        "observations": observations,
        "signals": signals,
        "privacy": {
            "raw_body_stored": False,
            "profile_contains_message_content": False,
        },
    }


def updated_profile(message: dict[str, Any], profile: dict[str, Any], *, message_ref: str) -> dict[str, Any]:
    current = dict(profile or empty_profile())
    refs = list(current.get("recent_message_refs") or [])
    if message_ref and message_ref in refs:
        return current

    current["observations"] = int(current.get("observations") or 0) + 1
    hour = _message_hour(message)
    if hour is not None:
        hours = dict(current.get("hours") or {})
        hours[str(hour)] = int(hours.get(str(hour)) or 0) + 1
        current["hours"] = hours

    reply_domain = _reply_domain(message)
    reply_domains = list(current.get("reply_domains") or [])
    if reply_domain and reply_domain not in reply_domains:
        reply_domains.append(reply_domain)
    current["reply_domains"] = reply_domains[-20:]

    if message.get("attachments"):
        current["attachment_messages"] = int(current.get("attachment_messages") or 0) + 1
    if _payment_language(message):
        current["payment_messages"] = int(current.get("payment_messages") or 0) + 1

    if message_ref:
        refs.append(message_ref)
    current["recent_message_refs"] = refs[-MAX_RECENT_REFS:]
    return current


def observe_sender_behavior(mailbox_address: str, message: dict[str, Any]) -> dict[str, Any] | None:
    sender = _sender(message)
    if not sender:
        return None
    key = f"imail:behavior:{mailbox_address.lower()}:{sender}"
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = client.get(key)
        profile = json.loads(raw) if raw else empty_profile()
        if not isinstance(profile, dict):
            profile = empty_profile()
        analysis = analyze_behavior(message, profile)
        message_ref = str(message.get("message_id") or f"uid:{message.get('uid') or ''}")[:512]
        next_profile = updated_profile(message, profile, message_ref=message_ref)
        client.setex(key, PROFILE_TTL_SECONDS, json.dumps(next_profile, separators=(",", ":"), sort_keys=True))
        return analysis
    except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError):
        return None
