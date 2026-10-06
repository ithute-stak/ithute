from app.services.mail_threat_canary import (
    automatic_rollback,
    baseline_floor,
    canary_validation,
    deterministic_canary_member,
    serving_source,
)


def _row(label: str, candidate: dict[str, float], baseline: dict[str, float], latency: float = 15.0):
    return {
        "verified_label": label,
        "candidate_probabilities": candidate,
        "baseline_probabilities": baseline,
        "latency_ms": latency,
    }


def test_canary_membership_is_deterministic_and_near_five_percent():
    first = [
        deterministic_canary_member(
            model_id="model-1",
            mailbox_id=f"mailbox-{index % 50}",
            message_ref=f"message-{index}",
        )
        for index in range(5000)
    ]
    second = [
        deterministic_canary_member(
            model_id="model-1",
            mailbox_id=f"mailbox-{index % 50}",
            message_ref=f"message-{index}",
        )
        for index in range(5000)
    ]

    assert first == second
    fraction = sum(first) / len(first)
    assert 0.035 <= fraction <= 0.065


def test_baseline_floor_never_reduces_existing_warning():
    result = baseline_floor(
        {
            "phishing_probability": 0.91,
            "bec_probability": 0.20,
            "recommended_action": "warn_and_verify",
        },
        {"legitimate": 0.95, "phishing": 0.03, "bec": 0.02},
    )

    assert result["recommended_action"] == "warn_and_verify"
    assert result["phishing_probability"] == 0.91
    assert result["baseline_preserved"] is True
    assert result["canary_can_reduce_risk"] is False


def test_canary_can_raise_risk_above_baseline():
    result = baseline_floor(
        {
            "phishing_probability": 0.10,
            "bec_probability": 0.10,
            "recommended_action": "allow",
        },
        {"legitimate": 0.05, "phishing": 0.90, "bec": 0.05},
    )

    assert result["recommended_action"] == "warn_and_verify"
    assert result["phishing_probability"] == 0.90


def test_strong_canary_can_become_activation_eligible():
    rows = []
    for _ in range(10):
        rows.append(_row(
            "legitimate",
            {"legitimate": 0.96, "phishing": 0.02, "bec": 0.02},
            {"legitimate": 0.70, "phishing": 0.15, "bec": 0.15},
        ))
        rows.append(_row(
            "phishing",
            {"legitimate": 0.02, "phishing": 0.96, "bec": 0.02},
            {"legitimate": 0.15, "phishing": 0.70, "bec": 0.15},
        ))
        rows.append(_row(
            "bec",
            {"legitimate": 0.02, "phishing": 0.02, "bec": 0.96},
            {"legitimate": 0.15, "phishing": 0.15, "bec": 0.70},
        ))

    result = canary_validation(rows)

    assert result["verified_canary_samples"] == 30
    assert result["enough_canary_samples"] is True
    assert result["eligible_for_activation"] is True


def test_automatic_rollback_waits_for_minimum_evidence():
    rows = [
        _row(
            "phishing",
            {"legitimate": 0.90, "phishing": 0.05, "bec": 0.05},
            {"legitimate": 0.10, "phishing": 0.80, "bec": 0.10},
        )
        for _ in range(10)
    ]

    result = automatic_rollback(rows)

    assert result["evaluated"] is False
    assert result["rollback"] is False


def test_automatic_rollback_triggers_for_bad_live_model():
    rows = []
    for _ in range(10):
        rows.append(_row(
            "legitimate",
            {"legitimate": 0.05, "phishing": 0.90, "bec": 0.05},
            {"legitimate": 0.90, "phishing": 0.05, "bec": 0.05},
            latency=350.0,
        ))
        rows.append(_row(
            "phishing",
            {"legitimate": 0.90, "phishing": 0.05, "bec": 0.05},
            {"legitimate": 0.05, "phishing": 0.90, "bec": 0.05},
            latency=350.0,
        ))
        rows.append(_row(
            "bec",
            {"legitimate": 0.90, "phishing": 0.05, "bec": 0.05},
            {"legitimate": 0.05, "phishing": 0.05, "bec": 0.90},
            latency=350.0,
        ))

    result = automatic_rollback(rows)

    assert result["evaluated"] is True
    assert result["rollback"] is True
    assert "recall" in result["reasons"]
    assert "latency" in result["reasons"]



def test_serving_route_keeps_active_champion_for_shadow_challenger():
    assert serving_source(
        challenger_state="shadow",
        canary_member=False,
        active_present=True,
    ) == "active"


def test_serving_route_keeps_active_for_non_canary_traffic():
    assert serving_source(
        challenger_state="canary",
        canary_member=False,
        active_present=True,
    ) == "active"


def test_serving_route_uses_challenger_only_for_canary_member():
    assert serving_source(
        challenger_state="canary",
        canary_member=True,
        active_present=True,
    ) == "challenger"


def test_serving_route_falls_back_to_baseline_without_active_champion():
    assert serving_source(
        challenger_state="qualified",
        canary_member=False,
        active_present=False,
    ) == "baseline"
