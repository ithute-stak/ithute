from app.services.hardware_model_evaluation import evaluate_candidate


def _row(target: int, candidate: float, baseline: float):
    return {
        "target": target,
        "candidate_probability": candidate,
        "baseline_probability": baseline,
    }


def test_candidate_can_become_shadow_eligible_but_not_active():
    rows = []
    for _ in range(12):
        rows.append(_row(1, 0.92, 0.78))
    for _ in range(12):
        rows.append(_row(0, 0.08, 0.22))

    result = evaluate_candidate(rows)
    assert result["promotion"]["eligible_for_shadow"] is True
    assert result["promotion"]["eligible_for_activation"] is False
    assert "shadow mode" in result["promotion"]["activation_reason"]


def test_high_false_positive_rate_blocks_promotion_even_with_good_recall():
    rows = []
    for _ in range(12):
        rows.append(_row(1, 0.95, 0.80))
    for _ in range(8):
        rows.append(_row(0, 0.75, 0.20))
    for _ in range(4):
        rows.append(_row(0, 0.10, 0.20))

    result = evaluate_candidate(rows)
    assert result["candidate"]["recall"] == 1.0
    assert result["candidate"]["false_positive_rate"] > 0.15
    assert result["promotion"]["eligible_for_shadow"] is False
    assert result["promotion"]["gates"]["false_positive_rate"] is False


def test_candidate_calibration_regression_blocks_promotion():
    rows = []
    for _ in range(12):
        rows.append(_row(1, 0.70, 0.90))
    for _ in range(12):
        rows.append(_row(0, 0.30, 0.10))

    result = evaluate_candidate(rows)
    assert result["candidate"]["f1"] == 1.0
    assert result["baseline"]["f1"] == 1.0
    assert result["candidate"]["brier_score"] > result["baseline"]["brier_score"]
    assert result["promotion"]["gates"]["brier_no_regression"] is False
    assert result["promotion"]["eligible_for_shadow"] is False


def test_small_evaluation_set_is_never_promotable():
    rows = [_row(1, 0.95, 0.80) for _ in range(8)]
    rows += [_row(0, 0.05, 0.20) for _ in range(8)]

    result = evaluate_candidate(rows)
    assert result["candidate"]["sample_count"] == 16
    assert result["promotion"]["gates"]["sample_count"] is False
    assert result["promotion"]["eligible_for_shadow"] is False
