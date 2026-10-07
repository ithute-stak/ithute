from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import getaddresses
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DomainIntelligenceProfile, SenderReputationProfile

MAX_RECENT_MESSAGE_REFS = 100


def sender_identity(message: dict[str, Any]) -> tuple[str, str, str]:
    addresses = [addr.lower() for _, addr in getaddresses([str(message.get("from") or "")]) if addr]
    sender = addresses[0] if addresses else ""
    domain = sender.rsplit("@", 1)[-1].strip(".") if "@" in sender else ""
    sender_hash = hashlib.sha256(sender.encode("utf-8")).hexdigest() if sender else ""
    return sender, domain, sender_hash


def _state(score: int, confidence: float) -> str:
    if confidence < 0.35:
        return "unknown"
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 45:
        return "neutral"
    if score >= 25:
        return "watch"
    return "poor"


def _confidence(observations: int, verified_total: int) -> float:
    observation_component = min(0.68, observations / 75.0)
    verdict_component = min(0.27, verified_total / 12.0)
    return round(min(0.98, 0.05 + observation_component + verdict_component), 3)


def _score(
    *,
    observations: int,
    authenticated: int,
    failures: int,
    suspicious_links: int,
    legitimate: int,
    phishing: int,
    bec: int,
    trusted_matches: int,
    domain_age_days: int | None = None,
    identity_status: str = "unverified",
) -> tuple[int, dict[str, Any]]:
    score = 50
    evidence: dict[str, Any] = {}
    denominator = max(1, observations)
    auth_rate = authenticated / denominator
    failure_rate = failures / denominator
    suspicious_rate = suspicious_links / denominator

    if observations >= 5 and auth_rate >= 0.95:
        score += 15
        evidence["authentication_consistency"] = "strong"
    elif observations >= 5 and auth_rate >= 0.80:
        score += 7
        evidence["authentication_consistency"] = "good"

    if failures:
        penalty = min(35, 8 + int(failure_rate * 70))
        score -= penalty
        evidence["authentication_failure_penalty"] = penalty

    if suspicious_links:
        penalty = min(25, 5 + int(suspicious_rate * 50))
        score -= penalty
        evidence["suspicious_link_penalty"] = penalty

    if legitimate:
        bonus = min(25, legitimate * 4)
        score += bonus
        evidence["verified_legitimate_bonus"] = bonus

    if phishing:
        penalty = min(55, 25 + phishing * 8)
        score -= penalty
        evidence["verified_phishing_penalty"] = penalty

    if bec:
        penalty = min(65, 35 + bec * 10)
        score -= penalty
        evidence["verified_bec_penalty"] = penalty

    if trusted_matches:
        bonus = min(12, 4 + trusted_matches // 3)
        score += bonus
        evidence["trusted_registry_bonus"] = bonus

    if domain_age_days is not None:
        if domain_age_days < 30:
            score -= 12
            evidence["new_domain_penalty"] = 12
        elif domain_age_days >= 365:
            score += 5
            evidence["established_domain_bonus"] = 5

    normalized_identity = str(identity_status or "unverified").lower()
    if normalized_identity in {"verified", "known_business", "known_government", "known_bank"}:
        score += 8
        evidence["domain_identity_bonus"] = 8
    elif normalized_identity in {"suspicious", "disposable", "impersonation"}:
        score -= 25
        evidence["domain_identity_penalty"] = 25

    score = max(0, min(100, score))
    evidence["auth_rate"] = round(auth_rate, 3)
    evidence["failure_rate"] = round(failure_rate, 3)
    evidence["suspicious_link_rate"] = round(suspicious_rate, 3)
    return score, evidence


def _recent_refs(profile: SenderReputationProfile | DomainIntelligenceProfile) -> list[str]:
    evidence = profile.evidence_json if isinstance(profile.evidence_json, dict) else {}
    refs = evidence.get("recent_message_refs")
    return [str(item) for item in refs] if isinstance(refs, list) else []


def _set_recent_refs(profile: SenderReputationProfile | DomainIntelligenceProfile, refs: list[str], score_evidence: dict[str, Any]) -> None:
    profile.evidence_json = {
        **score_evidence,
        "recent_message_refs": refs[-MAX_RECENT_MESSAGE_REFS:],
        "raw_message_content_stored": False,
    }


def reputation_context(db: Session, *, tenant_id: uuid.UUID, message: dict[str, Any]) -> dict[str, Any]:
    _sender, domain, sender_hash = sender_identity(message)
    if not sender_hash or not domain:
        return {"available": False, "sender": None, "domain": None, "risk_adjustment": 0}

    sender_profile = db.scalar(
        select(SenderReputationProfile).where(
            SenderReputationProfile.tenant_id == tenant_id,
            SenderReputationProfile.sender_hash == sender_hash,
        )
    )
    domain_profile = db.scalar(
        select(DomainIntelligenceProfile).where(
            DomainIntelligenceProfile.tenant_id == tenant_id,
            DomainIntelligenceProfile.domain == domain,
        )
    )

    sender_score = sender_profile.score if sender_profile is not None else 50
    sender_confidence = sender_profile.confidence if sender_profile is not None else 0.0
    domain_score = domain_profile.score if domain_profile is not None else 50
    domain_confidence = domain_profile.confidence if domain_profile is not None else 0.0
    confidence = max(sender_confidence, domain_confidence)
    combined_score = round(sender_score * 0.65 + domain_score * 0.35)

    adjustment = 0
    if confidence >= 0.45:
        if combined_score < 25:
            adjustment = 20
        elif combined_score < 40:
            adjustment = 12
        elif combined_score >= 85 and confidence >= 0.70:
            adjustment = -10
        elif combined_score >= 70 and confidence >= 0.60:
            adjustment = -5

    return {
        "available": sender_profile is not None or domain_profile is not None,
        "sender": {
            "score": sender_score,
            "state": sender_profile.state if sender_profile is not None else "unknown",
            "confidence": sender_confidence,
            "observations": sender_profile.observations if sender_profile is not None else 0,
        },
        "domain": {
            "name": domain,
            "score": domain_score,
            "state": domain_profile.state if domain_profile is not None else "unknown",
            "confidence": domain_confidence,
            "observations": domain_profile.observations if domain_profile is not None else 0,
            "domain_age_days": domain_profile.domain_age_days if domain_profile is not None else None,
            "identity_status": domain_profile.identity_status if domain_profile is not None else "unverified",
            "enrichment_source": domain_profile.enrichment_source if domain_profile is not None else None,
            "enrichment_checked_at": domain_profile.enrichment_checked_at.isoformat() if domain_profile is not None and domain_profile.enrichment_checked_at else None,
        },
        "combined_score": combined_score,
        "confidence": round(confidence, 3),
        "risk_adjustment": adjustment,
        "privacy": {
            "sender_address_stored": False,
            "sender_hash_algorithm": "sha256",
            "raw_message_content_stored": False,
        },
    }


def observe_reputation(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    message: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    _sender, domain, sender_hash = sender_identity(message)
    if not sender_hash or not domain:
        return reputation_context(db, tenant_id=tenant_id, message=message)

    message_ref = str(message.get("message_id") or f"uid:{message.get('uid') or ''}")[:512]
    message_ref_hash = hashlib.sha256(message_ref.encode("utf-8")).hexdigest()
    trust = intelligence.get("trust") if isinstance(intelligence.get("trust"), dict) else {}
    auth = trust.get("authentication") if isinstance(trust.get("authentication"), dict) else {}
    urls = trust.get("url_intelligence") if isinstance(trust.get("url_intelligence"), dict) else {}
    authenticated = bool(auth.get("authenticated"))
    auth_failure = bool(auth.get("any_failure"))
    suspicious_links = int(urls.get("suspicious_count") or 0) > 0
    registry_verified = bool(trust.get("verified"))

    sender_profile = db.scalar(
        select(SenderReputationProfile).where(
            SenderReputationProfile.tenant_id == tenant_id,
            SenderReputationProfile.sender_hash == sender_hash,
        )
    )
    if sender_profile is None:
        sender_profile = SenderReputationProfile(tenant_id=tenant_id, sender_hash=sender_hash, sender_domain=domain)
        db.add(sender_profile)
        db.flush()

    domain_profile = db.scalar(
        select(DomainIntelligenceProfile).where(
            DomainIntelligenceProfile.tenant_id == tenant_id,
            DomainIntelligenceProfile.domain == domain,
        )
    )
    if domain_profile is None:
        domain_profile = DomainIntelligenceProfile(tenant_id=tenant_id, domain=domain)
        db.add(domain_profile)
        db.flush()

    now = datetime.now(timezone.utc)
    for profile in (sender_profile, domain_profile):
        refs = _recent_refs(profile)
        if message_ref_hash in refs:
            continue
        refs.append(message_ref_hash)
        profile.observations += 1
        profile.authenticated_messages += int(authenticated)
        profile.authentication_failures += int(auth_failure)
        profile.suspicious_link_messages += int(suspicious_links)
        profile.last_seen_at = now

        if isinstance(profile, SenderReputationProfile):
            profile.registry_verified_messages += int(registry_verified)
            trusted_matches = profile.registry_verified_messages
            domain_age = None
            identity_status = "unverified"
        else:
            profile.trusted_registry_matches += int(registry_verified)
            trusted_matches = profile.trusted_registry_matches
            domain_age = profile.domain_age_days
            identity_status = profile.identity_status

        score, score_evidence = _score(
            observations=profile.observations,
            authenticated=profile.authenticated_messages,
            failures=profile.authentication_failures,
            suspicious_links=profile.suspicious_link_messages,
            legitimate=profile.verified_legitimate,
            phishing=profile.verified_phishing,
            bec=profile.verified_bec,
            trusted_matches=trusted_matches,
            domain_age_days=domain_age,
            identity_status=identity_status,
        )
        verified_total = profile.verified_legitimate + profile.verified_phishing + profile.verified_bec
        profile.confidence = _confidence(profile.observations, verified_total)
        profile.score = score
        profile.state = _state(score, profile.confidence)
        _set_recent_refs(profile, refs, score_evidence)

    db.flush()
    return reputation_context(db, tenant_id=tenant_id, message=message)


def record_verified_verdict(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    message: dict[str, Any],
    label: str,
) -> None:
    normalized = str(label or "").lower()
    if normalized not in {"legitimate", "phishing", "bec"}:
        return
    _sender, domain, sender_hash = sender_identity(message)
    if not sender_hash or not domain:
        return

    sender_profile = db.scalar(
        select(SenderReputationProfile).where(
            SenderReputationProfile.tenant_id == tenant_id,
            SenderReputationProfile.sender_hash == sender_hash,
        )
    )
    domain_profile = db.scalar(
        select(DomainIntelligenceProfile).where(
            DomainIntelligenceProfile.tenant_id == tenant_id,
            DomainIntelligenceProfile.domain == domain,
        )
    )
    if sender_profile is None or domain_profile is None:
        observe_reputation(db, tenant_id=tenant_id, message=message, intelligence={})
        sender_profile = db.scalar(select(SenderReputationProfile).where(SenderReputationProfile.tenant_id == tenant_id, SenderReputationProfile.sender_hash == sender_hash))
        domain_profile = db.scalar(select(DomainIntelligenceProfile).where(DomainIntelligenceProfile.tenant_id == tenant_id, DomainIntelligenceProfile.domain == domain))

    for profile in (sender_profile, domain_profile):
        if profile is None:
            continue
        field = "verified_legitimate" if normalized == "legitimate" else "verified_phishing" if normalized == "phishing" else "verified_bec"
        setattr(profile, field, int(getattr(profile, field) or 0) + 1)
        if isinstance(profile, SenderReputationProfile):
            trusted_matches = profile.registry_verified_messages
            domain_age = None
            identity_status = "unverified"
        else:
            trusted_matches = profile.trusted_registry_matches
            domain_age = profile.domain_age_days
            identity_status = profile.identity_status
        score, evidence = _score(
            observations=profile.observations,
            authenticated=profile.authenticated_messages,
            failures=profile.authentication_failures,
            suspicious_links=profile.suspicious_link_messages,
            legitimate=profile.verified_legitimate,
            phishing=profile.verified_phishing,
            bec=profile.verified_bec,
            trusted_matches=trusted_matches,
            domain_age_days=domain_age,
            identity_status=identity_status,
        )
        verified_total = profile.verified_legitimate + profile.verified_phishing + profile.verified_bec
        profile.confidence = _confidence(profile.observations, verified_total)
        profile.score = score
        profile.state = _state(score, profile.confidence)
        _set_recent_refs(profile, _recent_refs(profile), evidence)



def refresh_domain_profile(profile: DomainIntelligenceProfile) -> None:
    score, evidence = _score(
        observations=profile.observations,
        authenticated=profile.authenticated_messages,
        failures=profile.authentication_failures,
        suspicious_links=profile.suspicious_link_messages,
        legitimate=profile.verified_legitimate,
        phishing=profile.verified_phishing,
        bec=profile.verified_bec,
        trusted_matches=profile.trusted_registry_matches,
        domain_age_days=profile.domain_age_days,
        identity_status=profile.identity_status,
    )
    verified_total = profile.verified_legitimate + profile.verified_phishing + profile.verified_bec
    profile.confidence = _confidence(profile.observations, verified_total)
    profile.score = score
    profile.state = _state(score, profile.confidence)
    _set_recent_refs(profile, _recent_refs(profile), evidence)


def reputation_profile_payload(profile: SenderReputationProfile | DomainIntelligenceProfile) -> dict[str, Any]:
    base = {
        "id": str(profile.id),
        "score": profile.score,
        "state": profile.state,
        "confidence": profile.confidence,
        "observations": profile.observations,
        "authenticated_messages": profile.authenticated_messages,
        "authentication_failures": profile.authentication_failures,
        "suspicious_link_messages": profile.suspicious_link_messages,
        "verified_legitimate": profile.verified_legitimate,
        "verified_phishing": profile.verified_phishing,
        "verified_bec": profile.verified_bec,
        "first_seen_at": profile.first_seen_at.isoformat(),
        "last_seen_at": profile.last_seen_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }
    if isinstance(profile, SenderReputationProfile):
        return {
            **base,
            "kind": "sender",
            "sender_domain": profile.sender_domain,
            "registry_verified_messages": profile.registry_verified_messages,
        }
    return {
        **base,
        "kind": "domain",
        "domain": profile.domain,
        "trusted_registry_matches": profile.trusted_registry_matches,
        "domain_age_days": profile.domain_age_days,
        "identity_status": profile.identity_status,
        "enrichment_source": profile.enrichment_source,
        "enrichment_checked_at": profile.enrichment_checked_at.isoformat() if profile.enrichment_checked_at else None,
    }
