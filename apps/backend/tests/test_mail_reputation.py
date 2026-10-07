import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.mail_reputation import _score, _state, observe_reputation, record_verified_verdict, sender_identity


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



def test_sender_hash_is_tenant_scoped():
    message = {"from": "Alice <alice@example.com>"}
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    _sender_a, _domain_a, hash_a = sender_identity(message, tenant_id=tenant_a)
    _sender_b, _domain_b, hash_b = sender_identity(message, tenant_id=tenant_b)

    assert hash_a != hash_b
    assert "alice@example.com" not in hash_a


def test_observation_is_deduplicated_by_message_reference(db, tenant_admin):
    _user, tenant, _membership = tenant_admin
    message = {
        "from": "Alice <alice@example.com>",
        "message_id": "<same-message@example.com>",
        "authentication_results": "mx; spf=pass; dkim=pass; dmarc=pass",
        "received_spf": "pass",
        "body_text": "Routine message",
    }
    intelligence = {
        "trust": {
            "verified": False,
            "authentication": {"authenticated": True, "any_failure": False},
            "url_intelligence": {"suspicious_count": 0},
        }
    }

    first = observe_reputation(db, tenant_id=tenant.id, message=message, intelligence=intelligence)
    second = observe_reputation(db, tenant_id=tenant.id, message=message, intelligence=intelligence)

    assert first["sender"]["observations"] == 1
    assert second["sender"]["observations"] == 1
    assert second["domain"]["observations"] == 1


def test_verified_feedback_changes_durable_reputation(db, tenant_admin):
    _user, tenant, _membership = tenant_admin
    message = {
        "from": "Alice <alice@example.com>",
        "message_id": "<verdict-message@example.com>",
        "body_text": "Routine message",
    }
    observe_reputation(
        db,
        tenant_id=tenant.id,
        message=message,
        intelligence={"trust": {"authentication": {}, "url_intelligence": {}}},
    )
    record_verified_verdict(db, tenant_id=tenant.id, message=message, label="phishing")

    result = observe_reputation(
        db,
        tenant_id=tenant.id,
        message=message,
        intelligence={"trust": {"authentication": {}, "url_intelligence": {}}},
    )

    assert result["sender"]["score"] < 50
    assert result["domain"]["score"] < 50
