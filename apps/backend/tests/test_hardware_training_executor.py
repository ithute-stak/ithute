from app.services.hardware_training_executor import (
    artifact_fingerprint,
    dataset_fingerprint,
    deterministic_split,
    predict_probability,
    train_candidate,
    train_logistic,
)


def _row(index: int, target: int, server: str):
    base = 80.0 if target else 35.0
    return {
        "label_id": f"label-{index}",
        "server_id": server,
        "snapshot_id": f"snapshot-{index}",
        "target": target,
        "baseline_probability": 0.70 if target else 0.30,
        "features": {
            "temperature_celsius": base + index * 0.1,
            "memory_pressure_avg10": (20.0 if target else 4.0) + index * 0.01,
            "io_pressure_avg10": (25.0 if target else 5.0) + index * 0.01,
            "filesystem_used_percent": (92.0 if target else 55.0) + index * 0.01,
            "storage_warning_count": 3.0 if target else 0.0,
            "health_score": 35.0 if target else 90.0,
        },
    }


def _dataset():
    rows = []
    for index in range(40):
        target = 1 if index % 2 == 0 else 0
        rows.append(_row(index, target, f"server-{index % 4}"))
    return rows


def test_split_is_deterministic_and_non_empty():
    rows = _dataset()
    first = deterministic_split(rows)
    second = deterministic_split(rows)

    assert [row["label_id"] for row in first.train] == [row["label_id"] for row in second.train]
    assert [row["label_id"] for row in first.validation] == [row["label_id"] for row in second.validation]
    assert first.train
    assert first.validation


def test_training_artifact_is_reproducible():
    rows = _dataset()
    split = deterministic_split(rows)
    first = train_logistic(split.train)
    second = train_logistic(split.train)

    assert first == second
    assert artifact_fingerprint(first) == artifact_fingerprint(second)


def test_dataset_fingerprint_is_order_independent():
    rows = _dataset()
    assert dataset_fingerprint(rows) == dataset_fingerprint(list(reversed(rows)))


def test_candidate_version_and_hash_are_reproducible():
    first = train_candidate(_dataset())
    second = train_candidate(_dataset())

    assert first["version"] == second["version"]
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["dataset_sha256"] == second["dataset_sha256"]


def test_candidate_emits_validation_probabilities():
    candidate = train_candidate(_dataset())

    assert candidate["training_rows"] > 0
    assert candidate["validation_rows"] > 0
    assert candidate["evaluation_rows"]
    assert all(0.0 <= row["candidate_probability"] <= 1.0 for row in candidate["evaluation_rows"])


def test_trained_model_separates_clear_failure_signal():
    rows = _dataset()
    split = deterministic_split(rows)
    artifact = train_logistic(split.train)

    positive = _row(100, 1, "server-x")
    negative = _row(101, 0, "server-y")

    assert predict_probability(artifact, positive) > predict_probability(artifact, negative)


def test_artifact_contains_only_training_fitted_standardizer():
    candidate = train_candidate(_dataset())
    artifact = candidate["artifact"]

    assert set(artifact["standardizer"]) == {
        "temperature_celsius",
        "memory_pressure_avg10",
        "io_pressure_avg10",
        "filesystem_used_percent",
        "storage_warning_count",
        "health_score",
    }
    assert artifact["train_rows"] == candidate["training_rows"]
