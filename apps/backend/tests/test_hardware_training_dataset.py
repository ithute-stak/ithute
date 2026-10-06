from types import SimpleNamespace

from app.services.hardware_training_dataset import build_training_example, dataset_summary


def _label(label: str, confidence: float = 0.95, server: str = "server-1"):
    return SimpleNamespace(
        id="label-1",
        incident_id="incident-1",
        server_id=server,
        label=label,
        component="storage",
        confidence=confidence,
    )


def _snapshot(**overrides):
    values = {
        "id": "snapshot-1",
        "temperature_celsius": 72.0,
        "memory_pressure_avg10": 8.0,
        "io_pressure_avg10": 14.0,
        "filesystem_used_percent": 70.0,
        "storage_warning_count": 1,
        "health_score": 62,
        "predictive_risk_score": 78,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_training_example_maps_binary_labels_and_baseline_probability():
    positive = build_training_example(_label("confirmed_failure"), _snapshot())
    negative = build_training_example(_label("false_positive"), _snapshot(predictive_risk_score=20))

    assert positive is not None
    assert positive["target"] == 1
    assert positive["baseline_probability"] == 0.78
    assert "predictive_risk_score" not in positive["features"]

    assert negative is not None
    assert negative["target"] == 0
    assert negative["baseline_probability"] == 0.2


def test_training_example_excludes_non_binary_labels():
    assert build_training_example(_label("confirmed_degradation"), _snapshot()) is None
    assert build_training_example(_label("inconclusive"), _snapshot()) is None


def test_training_example_requires_sufficient_raw_features():
    example = build_training_example(
        _label("confirmed_failure"),
        _snapshot(
            temperature_celsius=None,
            memory_pressure_avg10=None,
            io_pressure_avg10=None,
            filesystem_used_percent=None,
        ),
    )
    assert example is None


def test_dataset_summary_reports_balance_servers_and_feature_coverage():
    examples = [
        build_training_example(_label("confirmed_failure", server="server-1"), _snapshot()),
        build_training_example(_label("confirmed_failure", server="server-2"), _snapshot()),
        build_training_example(_label("false_positive", server="server-3"), _snapshot(storage_warning_count=None)),
    ]
    rows = [row for row in examples if row is not None]
    summary = dataset_summary(rows)

    assert summary["examples"] == 3
    assert summary["positive_examples"] == 2
    assert summary["negative_examples"] == 1
    assert summary["distinct_servers"] == 3
    assert summary["feature_coverage"]["temperature_celsius"] == 3
    assert summary["feature_coverage"]["storage_warning_count"] == 2
