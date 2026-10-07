import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.mail_reputation import _score, _state, reputation_context


def test_reputation_score_rewards_consistent_authenticated_history():
    score, evidence = _score(
        observations=20,
        authenticated=20,
        failures=0,
        suspicious_links=0,
        legitimate=4,
        phishing=0,
        bec=0,
        trusted_matches=5,
    )

    assert score >= 80
    assert evidence["authentication_consistency"] == "strong"
    assert evidence["verified_legitimate_bonus"] > 0


def test_verified_bec_history_dominates_positive_history():
    score, evidence = _score(
        observations=30,
        authenticated=29,
        failures=1,
        suspicious_links=0,
        legitimate=5,
        phishing=0,
        bec=2,
        trusted_matches=10,
    )

    assert score < 50
    assert evidence["verified_bec_penalty"] >= 45


def test_new_or_suspicious_domain_enrichment_is_bounded_but_negative():
    young, young_evidence = _score(
        observations=10,
        authenticated=10,
        failures=0,
        suspicious_links=0,
        legitimate=0,
        phishing=0,
        bec=0,
        trusted_matches=0,
        domain_age_days=7,
        identity_status="unverified",
    )
    suspicious, suspicious_evidence = _score(
        observations=10,
        authenticated=10,
        failures=0,
        suspicious_links=0,
        legitimate=0,
        phishing=0,
        bec=0,
        trusted_matches=0,
        domain_age_days=500,
        identity_status="impersonation",
    )

    assert young_evidence["new_domain_penalty"] == 12
    assert suspicious_evidence["domain_identity_penalty"] == 25
    assert suspicious < young


def test_state_requires_confidence_before_calling_sender_good():
    assert _state(95, 0.2) == "unknown"
    assert _state(85, 0.8) == "strong"
    assert _state(20, 0.8) == "poor"
