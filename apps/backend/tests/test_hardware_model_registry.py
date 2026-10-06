from app.services.hardware_model_registry import (
    model_quality_score,
    registry_summary,
    validate_transition,
)


def test_model_cannot_skip_shadow_or_canary():
    assert validate_transition("candidate", "active")["valid"] is False
    assert validate_transition("candidate", "shadow")["valid"] is True
    assert validate_transition("qualified", "active")["valid"] is False
    assert validate_transition("qualified", "canary")["valid"] is True


def test_retired_model_cannot_reactivate():
    result = validate_transition("retired_or_rolled_back", "active")
    assert result["valid"] is False
    assert result["allowed_targets"] == []


def test_quality_score_rewards_safe_recall_and_low_false_positive_rate():
    strong = model_quality_score({
        "precision": 0.90,
        "recall": 0.90,
        "f1": 0.90,
        "false_positive_rate": 0.05,
        "brier_score": 0.10,
        "expected_calibration_error": 0.05,
        "population_stability_index": 0.05,
    })
    weak = model_quality_score({
        "precision": 0.90,
        "recall": 0.50,
        "f1": 0.65,
        "false_positive_rate": 0.30,
        "brier_score": 0.20,
        "expected_calibration_error": 0.10,
        "population_stability_index": 0.15,
    })
    assert strong > weak


def test_registry_summary_surfaces_active_and_ranked_models():
    summary = registry_summary([
        {
            "name": "hardware-xgb",
            "version": "v1",
            "lifecycle_state": "shadow",
            "shadow_metrics": {"precision": 0.85, "recall": 0.80, "f1": 0.82, "false_positive_rate": 0.08},
        },
        {
            "name": "hardware-xgb",
            "version": "v2",
            "lifecycle_state": "active",
            "shadow_metrics": {"precision": 0.90, "recall": 0.88, "f1": 0.89, "false_positive_rate": 0.05},
        },
    ])
    assert summary["total_models"] == 2
    assert summary["counts"]["active"] == 1
    assert summary["active_model"]["version"] == "v2"
    assert summary["ranked_models"][0]["version"] == "v2"
