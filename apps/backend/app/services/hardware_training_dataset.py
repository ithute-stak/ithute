from __future__ import annotations

from typing import Any


TRAINING_FEATURES = (
    "temperature_celsius",
    "memory_pressure_avg10",
    "io_pressure_avg10",
    "filesystem_used_percent",
    "storage_warning_count",
    "health_score",
)

BINARY_TARGETS = {
    "confirmed_failure": 1,
    "false_positive": 0,
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def build_training_example(label: Any, snapshot: Any) -> dict[str, Any] | None:
    label_name = str(getattr(label, "label", "") or "")
    if label_name not in BINARY_TARGETS:
        return None

    features: dict[str, float] = {}
    for name in TRAINING_FEATURES:
        value = _number(getattr(snapshot, name, None))
        if value is not None:
            features[name] = value

    if len(features) < 4:
        return None

    risk = _number(getattr(snapshot, "predictive_risk_score", None))
    baseline_probability = max(0.0, min(1.0, (risk or 0.0) / 100.0))
    return {
        "label_id": str(getattr(label, "id", "")),
        "incident_id": str(getattr(label, "incident_id", "")),
        "server_id": str(getattr(label, "server_id", "")),
        "snapshot_id": str(getattr(snapshot, "id", "")),
        "target": BINARY_TARGETS[label_name],
        "features": features,
        "baseline_probability": round(baseline_probability, 6),
        "label_confidence": round(float(getattr(label, "confidence", 0.0) or 0.0), 4),
        "component": str(getattr(label, "component", "unknown") or "unknown"),
    }


def dataset_summary(examples: list[dict[str, Any]]) -> dict[str, Any]:
    positives = sum(1 for row in examples if int(row["target"]) == 1)
    negatives = sum(1 for row in examples if int(row["target"]) == 0)
    servers = {str(row["server_id"]) for row in examples}
    components = sorted({str(row.get("component") or "unknown") for row in examples})
    feature_coverage = {
        name: sum(1 for row in examples if name in row.get("features", {}))
        for name in TRAINING_FEATURES
    }
    return {
        "examples": len(examples),
        "positive_examples": positives,
        "negative_examples": negatives,
        "distinct_servers": len(servers),
        "components": components,
        "features": list(TRAINING_FEATURES),
        "feature_coverage": feature_coverage,
    }
