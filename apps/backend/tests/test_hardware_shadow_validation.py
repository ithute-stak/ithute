from app.services.hardware_shadow_validation import (
    expected_calibration_error,
    page_hinkley_change,
    population_stability_index,
    rollback_decision,
    shadow_policy,
    shadow_validation,
)


def _row(target: int, candidate: float, baseline: float):
    return {
        "target": target,
        "candidate_probability": candidate,
        "baseline_probability": baseline,
    }


def test_well_calibrated_shadow_candidate_can_qualify_for_canary():
    rows = []
    for _ in range(30):
        rows.append(_row(1, 0.95, 0.80))
    for _ in range(30):
        rows.append(_row(0, 0.05, 0.20))

    result = shadow_validation(rows)
    assert result["eligible_for_canary"] is True
    assert result["canary_fraction"] == 0.05
    assert all(result["gates"].values())


def test_population_drift_blocks_canary():
    reference = [0.05] * 30 + [0.95] * 30
    rows = [_row(1, 0.55, 0.95) for _ in range(30)]
    rows += [_row(0, 0.45, 0.05) for _ in range(30)]

    result = shadow_validation(rows, reference_probabilities=reference)
    assert result["population_stability_index"] > 0.20
    assert result["gates"]["population_drift"] is False
    assert result["eligible_for_canary"] is False


def test_calibration_error_detects_overconfident_probabilities():
    rows = [_row(1, 0.99, 0.80) for _ in range(10)]
    rows += [_row(0, 0.99, 0.20) for _ in range(10)]
    assert expected_calibration_error(rows) > 0.40


def test_page_hinkley_detects_residual_regime_change():
    residuals = [0.02] * 20 + [0.45] * 20
    result = page_hinkley_change(residuals)
    assert result["change_detected"] is True


def test_psi_is_small_for_similar_distributions():
    reference = [0.05, 0.10, 0.15, 0.80, 0.85, 0.90] * 10
    current = [0.06, 0.11, 0.16, 0.79, 0.84, 0.89] * 10
    assert population_stability_index(reference, current) < 0.20


def test_canary_rolls_back_to_robust_ensemble_on_safety_regression():
    decision = rollback_decision(
        {
            "recall": 0.60,
            "false_positive_rate": 0.08,
            "expected_calibration_error": 0.08,
            "population_stability_index": 0.10,
        }
    )
    assert decision["rollback_required"] is True
    assert "recall_below_floor" in decision["reasons"]
    assert decision["fallback"] == "robust_ensemble_baseline"


def test_shadow_policy_exposes_lifecycle_and_ai_algorithms():
    policy = shadow_policy()
    assert policy["lifecycle"] == [
        "candidate",
        "shadow",
        "qualified",
        "canary",
        "active",
        "retired_or_rolled_back",
    ]
    assert "expected_calibration_error" in policy["algorithms"]
    assert "population_stability_index" in policy["algorithms"]
    assert "page_hinkley_change_detection" in policy["algorithms"]
    assert policy["automatic_rollback"]["fallback"] == "robust_ensemble_baseline"
