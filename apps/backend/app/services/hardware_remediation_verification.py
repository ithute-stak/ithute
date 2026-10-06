from __future__ import annotations

from statistics import median
from typing import Any, Sequence


MIN_VERIFICATION_SAMPLES = 3
TARGET_VERIFICATION_SAMPLES = 6


METRICS = {
    "health_score": {"direction": 1.0, "scale": 20.0, "label": "health score"},
    "predictive_risk_score": {"direction": -1.0, "scale": 25.0, "label": "predictive risk"},
    "temperature_celsius": {"direction": -1.0, "scale": 8.0, "label": "temperature"},
    "memory_pressure_avg10": {"direction": -1.0, "scale": 8.0, "label": "memory pressure"},
    "io_pressure_avg10": {"direction": -1.0, "scale": 8.0, "label": "I/O pressure"},
    "filesystem_used_percent": {"direction": -1.0, "scale": 8.0, "label": "filesystem usage"},
    "storage_warning_count": {"direction": -1.0, "scale": 1.0, "label": "storage warnings"},
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if value == value and value not in {float("inf"), float("-inf")} else None


def _relevant_metrics(action: str) -> list[str]:
    action = (action or "").lower()
    base = ["health_score", "predictive_risk_score"]
    if "cooling" in action or "thermal" in action:
        return base + ["temperature_celsius"]
    if "memory" in action:
        return base + ["memory_pressure_avg10"]
    if "filesystem" in action or "capacity" in action:
        return base + ["filesystem_used_percent"]
    if "smart" in action or "nvme" in action or "storage_replacement" in action:
        return base + ["storage_warning_count", "io_pressure_avg10"]
    if "storage" in action or "io_" in action or "latency" in action:
        return base + ["io_pressure_avg10", "storage_warning_count"]
    return base + [
        "temperature_celsius",
        "memory_pressure_avg10",
        "io_pressure_avg10",
        "filesystem_used_percent",
        "storage_warning_count",
    ]


def verify_remediation(
    baseline: dict[str, Any],
    post_samples: Sequence[dict[str, Any]],
    action: str,
) -> dict[str, Any]:
    samples = list(post_samples)[-TARGET_VERIFICATION_SAMPLES:]
    if len(samples) < MIN_VERIFICATION_SAMPLES:
        return {
            "ready": False,
            "outcome": "",
            "confidence": round(len(samples) / MIN_VERIFICATION_SAMPLES, 3),
            "sample_count": len(samples),
            "evidence": [
                f"Collecting post-remediation telemetry: {len(samples)}/{MIN_VERIFICATION_SAMPLES} minimum samples"
            ],
            "metrics": [],
        }

    comparisons: list[dict[str, Any]] = []
    for name in _relevant_metrics(action):
        definition = METRICS[name]
        before = _number(baseline.get(name))
        after_values = [_number(sample.get(name)) for sample in samples]
        clean = [value for value in after_values if value is not None]
        if before is None or not clean:
            continue

        after = median(clean)
        direction = float(definition["direction"])
        scale = max(0.1, float(definition["scale"]))
        normalized = max(-1.0, min(1.0, direction * (after - before) / scale))
        comparisons.append({
            "name": name,
            "label": definition["label"],
            "before": round(before, 3),
            "after_median": round(after, 3),
            "improvement": round(normalized, 3),
        })

    if not comparisons:
        return {
            "ready": False,
            "outcome": "",
            "confidence": 0.0,
            "sample_count": len(samples),
            "evidence": ["Post-remediation samples do not contain enough comparable hardware signals"],
            "metrics": [],
        }

    # Overall health and predictive risk are important for every remediation,
    # while the action-specific signal prevents unrelated improvements from
    # falsely validating a repair.
    weights = []
    scores = []
    for item in comparisons:
        weight = 1.35 if item["name"] in {"health_score", "predictive_risk_score"} else 1.0
        weights.append(weight)
        scores.append(float(item["improvement"]) * weight)
    composite = sum(scores) / max(sum(weights), 1e-6)

    latest = samples[-1]
    latest_health = _number(latest.get("health_score"))
    latest_risk = _number(latest.get("predictive_risk_score"))
    confidence = min(1.0, len(samples) / TARGET_VERIFICATION_SAMPLES) * min(1.0, len(comparisons) / 3.0)

    if composite >= 0.45 and (latest_health is None or latest_health >= 80) and (latest_risk is None or latest_risk < 50):
        outcome = "resolved"
    elif composite >= 0.18:
        outcome = "improved"
    elif composite <= -0.18:
        outcome = "worsened"
    else:
        outcome = "no_change"

    ranked = sorted(comparisons, key=lambda item: abs(float(item["improvement"])), reverse=True)
    evidence = [
        (
            f"{item['label']}: {item['before']:.1f} -> {item['after_median']:.1f} "
            f"({'improved' if float(item['improvement']) > 0.05 else 'worsened' if float(item['improvement']) < -0.05 else 'stable'})"
        )
        for item in ranked[:5]
    ]
    evidence.append(f"Measured remediation composite={composite:.2f} from {len(samples)} post-remediation samples")

    return {
        "ready": True,
        "outcome": outcome,
        "confidence": round(confidence, 3),
        "sample_count": len(samples),
        "composite": round(composite, 3),
        "evidence": evidence,
        "metrics": comparisons,
    }
