from app.services.hardware_supervised_learning import supervised_training_readiness


def _labels(label: str, count: int, *, confidence: float = 0.95, server_offset: int = 0):
    return [
        {
            "label": label,
            "component": "storage" if index % 2 == 0 else "memory",
            "confidence": confidence,
            "server_id": f"server-{server_offset + (index % 4)}",
        }
        for index in range(count)
    ]


def test_supervised_readiness_blocks_small_dataset():
    result = supervised_training_readiness(
        _labels("confirmed_failure", 5) + _labels("false_positive", 5, server_offset=10)
    )
    assert result["ready"] is False
    assert result["binary_labels"] == 10
    assert result["gates"]["total_binary_labels"] is False
    assert result["blockers"]


def test_supervised_readiness_ignores_low_confidence_binary_labels():
    rows = (
        _labels("confirmed_failure", 20, confidence=0.95)
        + _labels("false_positive", 20, confidence=0.60, server_offset=10)
    )
    result = supervised_training_readiness(rows)
    assert result["ready"] is False
    assert result["confirmed_failures"] == 20
    assert result["false_positives"] == 0
    assert result["high_confidence_labels"] == 20


def test_supervised_readiness_blocks_severe_class_imbalance():
    rows = (
        _labels("confirmed_failure", 36, confidence=0.95)
        + _labels("false_positive", 12, confidence=0.95, server_offset=10)
    )
    result = supervised_training_readiness(rows)
    assert result["ready"] is True
    assert result["class_imbalance_ratio"] == 3.0

    rows += _labels("confirmed_failure", 1, confidence=0.95, server_offset=20)
    result = supervised_training_readiness(rows)
    assert result["ready"] is False
    assert result["gates"]["class_balance"] is False


def test_supervised_readiness_turns_green_only_when_all_gates_pass():
    rows = (
        _labels("confirmed_failure", 20, confidence=0.95)
        + _labels("false_positive", 20, confidence=0.95, server_offset=10)
        + _labels("confirmed_degradation", 8, confidence=0.99, server_offset=20)
        + _labels("inconclusive", 3, confidence=0.99, server_offset=30)
    )
    result = supervised_training_readiness(rows)
    assert result["ready"] is True
    assert result["binary_labels"] == 40
    assert result["confirmed_failures"] == 20
    assert result["false_positives"] == 20
    assert result["distinct_servers"] >= 3
    assert all(result["gates"].values())
    assert result["engine"] == "xgboost-compatible"
