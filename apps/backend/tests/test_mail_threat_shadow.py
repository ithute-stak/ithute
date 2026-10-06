from app.services.mail_threat_shadow import (
    baseline_probabilities,
    population_stability_index,
    rollback_decision,
    shadow_validation,
)


def _row(label: str, candidate: dict[str, float], baseline: dict[str, float], latency: float = 20.0):
    return {
        "verified_label": label,
        "candidate_probabilities": candidate,
        "baseline_probabilities": baseline,
        "latency_ms": latency,
    }


def test_baseline_probabilities_are_normalized():
    result = baseline_probabilities(0.8, 0.4)

    assert abs(sum(result.values()) - 1.0) < 1e-6
    assert result["phishing"] > result["bec"]


def test_population_stability_is_zero_for_same_distribution():
    distribution = {"legitimate": 0.6, "phishing": 0.2, "bec": 0.2}
    assert population_stability_index(distribution, distribution) == 0.0


def test_shadow_validation_qualifies_strong_candidate():
    rows = []
    for _ in range(20):
        rows.append(_row(
            "legitimate",
            {"legitimate": 0.95, "phishing": 0.03, "bec": 0.02},
            {"legitimate": 0.70, "phishing": 0.20, "bec": 0.10},
        ))
        rows.append(_row(
            "phishing",
            {"legitimate": 0.02, "phishing": 0.95, "bec": 0.03},
            {"legitimate": 0.20, "phishing": 0.65, "bec": 0.15},
        ))
        rows.append(_row(
            "bec",
            {"legitimate": 0.02, "phishing": 0.03, "bec": 0.95},
            {"legitimate": 0.20, "phishing": 0.20, "bec": 0.60},
        ))

    result = shadow_validation(rows)

    assert result["eligible_for_canary"] is True
    assert result["eligible_for_activation"] is False


def test_shadow_validation_blocks_bad_calibration_or_drift():
    rows = []
    for _ in range(20):
        rows.append(_row(
            "legitimate",
            {"legitimate": 0.34, "phishing": 0.33, "bec": 0.33},
            {"legitimate": 0.90, "phishing": 0.05, "bec": 0.05},
        ))
        rows.append(_row(
            "phishing",
            {"legitimate": 0.34, "phishing": 0.33, "bec": 0.33},
            {"legitimate": 0.05, "phishing": 0.90, "bec": 0.05},
        ))
        rows.append(_row(
            "bec",
            {"legitimate": 0.34, "phishing": 0.33, "bec": 0.33},
            {"legitimate": 0.05, "phishing": 0.05, "bec": 0.90},
        ))

    result = shadow_validation(rows)

    assert result["eligible_for_canary"] is False
    assert result["gates"]["calibration"] is False or result["gates"]["recall_no_regression"] is False


def test_rollback_triggers_on_recall_and_latency():
    result = rollback_decision({
        "candidate": {
            "macro_recall": 0.50,
            "multiclass_brier": 0.10,
            "expected_calibration_error": 0.05,
        },
        "population_stability_index": 0.10,
        "mean_latency_ms": 400.0,
    })

    assert result["rollback"] is True
    assert "recall" in result["reasons"]
    assert "latency" in result["reasons"]
