from __future__ import annotations

import hashlib
from typing import Any, Iterable

from app.services.mail_threat_shadow import rollback_decision, shadow_validation

CANARY_FRACTION = 0.05
MIN_CANARY_VERIFIED_SAMPLES = 30
ACTION_RANK = {"allow": 0, "review": 1, "warn_and_verify": 2}


def deterministic_canary_member(
    *,
    model_id: str,
    mailbox_id: str,
    message_ref: str,
    fraction: float = CANARY_FRACTION,
) -> bool:
    bounded = max(0.0, min(1.0, float(fraction)))
    if bounded <= 0.0:
        return False
    if bounded >= 1.0:
        return True
    key = f"{model_id}|{mailbox_id}|{message_ref}".encode("utf-8")
    bucket = int(hashlib.sha256(key).hexdigest()[:8], 16) / 0xFFFFFFFF
    return bucket < bounded


def candidate_action(probabilities: dict[str, Any]) -> str:
    phishing = float(probabilities.get("phishing") or 0.0)
    bec = float(probabilities.get("bec") or 0.0)
    threat = max(phishing, bec)
    if threat >= 0.80:
        return "warn_and_verify"
    if threat >= 0.55:
        return "review"
    return "allow"


def baseline_floor(
    baseline_security: dict[str, Any],
    candidate_probabilities: dict[str, Any],
) -> dict[str, Any]:
    baseline_action = str(baseline_security.get("recommended_action") or "allow")
    model_action = candidate_action(candidate_probabilities)
    effective_action = (
        model_action
        if ACTION_RANK.get(model_action, 0) > ACTION_RANK.get(baseline_action, 0)
        else baseline_action
    )
    baseline_phishing = float(baseline_security.get("phishing_probability") or 0.0)
    baseline_bec = float(baseline_security.get("bec_probability") or 0.0)
    candidate_phishing = float(candidate_probabilities.get("phishing") or 0.0)
    candidate_bec = float(candidate_probabilities.get("bec") or 0.0)
    return {
        "phishing_probability": round(max(baseline_phishing, candidate_phishing), 3),
        "bec_probability": round(max(baseline_bec, candidate_bec), 3),
        "recommended_action": effective_action,
        "baseline_action": baseline_action,
        "candidate_action": model_action,
        "baseline_preserved": ACTION_RANK.get(effective_action, 0) >= ACTION_RANK.get(baseline_action, 0),
        "canary_can_reduce_risk": False,
    }


def canary_validation(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    validation = shadow_validation(data)
    validation["verified_canary_samples"] = len(data)
    validation["minimum_verified_canary_samples"] = MIN_CANARY_VERIFIED_SAMPLES
    validation["enough_canary_samples"] = len(data) >= MIN_CANARY_VERIFIED_SAMPLES
    validation["eligible_for_activation"] = (
        validation["enough_canary_samples"]
        and validation["eligible_for_canary"]
    )
    return validation


def automatic_rollback(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    if len(data) < MIN_CANARY_VERIFIED_SAMPLES:
        return {
            "evaluated": False,
            "rollback": False,
            "reasons": [],
            "verified_samples": len(data),
            "minimum_verified_samples": MIN_CANARY_VERIFIED_SAMPLES,
            "fallback": "ithute-mail-intelligence-v1",
        }
    validation = shadow_validation(data)
    decision = rollback_decision(validation)
    return {
        "evaluated": True,
        "rollback": bool(decision["rollback"]),
        "reasons": list(decision["reasons"]),
        "verified_samples": len(data),
        "minimum_verified_samples": MIN_CANARY_VERIFIED_SAMPLES,
        "fallback": decision["fallback"],
        "validation": validation,
        "thresholds": decision["thresholds"],
    }


def canary_policy() -> dict[str, Any]:
    return {
        "fraction": CANARY_FRACTION,
        "minimum_verified_samples": MIN_CANARY_VERIFIED_SAMPLES,
        "deterministic": True,
        "baseline_is_safety_floor": True,
        "canary_can_reduce_risk": False,
        "direct_activation_allowed": False,
        "automatic_rollback_enabled": True,
        "fallback": "ithute-mail-intelligence-v1",
    }
