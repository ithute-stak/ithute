from __future__ import annotations

import math
from typing import Any, Iterable

from app.services.mail_threat_model import CLASSES, multiclass_metrics

MIN_SHADOW_SAMPLES = 50
MIN_MACRO_PRECISION = 0.82
MIN_MACRO_RECALL = 0.75
MAX_BRIER = 0.20
MAX_ECE = 0.10
MAX_CLASS_DISTRIBUTION_PSI = 0.20

ROLLBACK_MIN_MACRO_RECALL = 0.68
ROLLBACK_MAX_BRIER = 0.26
ROLLBACK_MAX_ECE = 0.16
ROLLBACK_MAX_PSI = 0.30
ROLLBACK_MAX_LATENCY_MS = 250.0
EPSILON = 1e-6


def baseline_probabilities(phishing_probability: float, bec_probability: float) -> dict[str, float]:
    phishing = max(0.0, min(1.0, float(phishing_probability)))
    bec = max(0.0, min(1.0, float(bec_probability)))
    legitimate = max(0.0, 1.0 - max(phishing, bec))
    raw = {
        "legitimate": legitimate,
        "phishing": phishing,
        "bec": bec,
    }
    total = sum(raw.values()) or 1.0
    return {label: round(raw[label] / total, 8) for label in CLASSES}


def class_distribution(rows: Iterable[dict[str, Any]], probability_key: str) -> dict[str, float]:
    data = list(rows)
    totals = {label: 0.0 for label in CLASSES}
    for row in data:
        probabilities = row.get(probability_key) if isinstance(row.get(probability_key), dict) else {}
        for label in CLASSES:
            totals[label] += float(probabilities.get(label) or 0.0)
    denominator = max(1, len(data))
    return {label: totals[label] / denominator for label in CLASSES}


def population_stability_index(expected: dict[str, float], actual: dict[str, float]) -> float:
    psi = 0.0
    for label in CLASSES:
        exp = max(EPSILON, float(expected.get(label) or 0.0))
        act = max(EPSILON, float(actual.get(label) or 0.0))
        psi += (act - exp) * math.log(act / exp)
    return round(psi, 6)


def _metric_rows(rows: list[dict[str, Any]], probability_key: str) -> list[dict[str, Any]]:
    return [
        {
            "label": str(row["verified_label"]),
            "probabilities": dict(row[probability_key]),
        }
        for row in rows
    ]


def shadow_validation(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    matured = [
        row for row in rows
        if str(row.get("verified_label") or "") in CLASSES
        and isinstance(row.get("candidate_probabilities"), dict)
        and isinstance(row.get("baseline_probabilities"), dict)
    ]
    candidate = multiclass_metrics(_metric_rows(matured, "candidate_probabilities"))
    baseline = multiclass_metrics(_metric_rows(matured, "baseline_probabilities"))

    candidate_distribution = class_distribution(matured, "candidate_probabilities")
    baseline_distribution = class_distribution(matured, "baseline_probabilities")
    psi = population_stability_index(baseline_distribution, candidate_distribution)

    latency_values = [
        float(row["latency_ms"])
        for row in matured
        if row.get("latency_ms") is not None
    ]
    mean_latency = sum(latency_values) / len(latency_values) if latency_values else 0.0

    gates = {
        "sample_count": len(matured) >= MIN_SHADOW_SAMPLES,
        "macro_precision": float(candidate.get("macro_precision") or 0.0) >= MIN_MACRO_PRECISION,
        "macro_recall": float(candidate.get("macro_recall") or 0.0) >= MIN_MACRO_RECALL,
        "brier": float(candidate.get("multiclass_brier") if candidate.get("multiclass_brier") is not None else 1.0) <= MAX_BRIER,
        "calibration": float(candidate.get("expected_calibration_error") if candidate.get("expected_calibration_error") is not None else 1.0) <= MAX_ECE,
        "class_distribution_drift": psi <= MAX_CLASS_DISTRIBUTION_PSI,
        "recall_no_regression": float(candidate.get("macro_recall") or 0.0) >= float(baseline.get("macro_recall") or 0.0),
        "precision_no_regression": float(candidate.get("macro_precision") or 0.0) >= float(baseline.get("macro_precision") or 0.0),
        "brier_no_regression": float(candidate.get("multiclass_brier") if candidate.get("multiclass_brier") is not None else 1.0) <= float(baseline.get("multiclass_brier") if baseline.get("multiclass_brier") is not None else 1.0),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "eligible_for_canary": all(gates.values()),
        "eligible_for_activation": False,
        "candidate": candidate,
        "baseline": baseline,
        "population_stability_index": psi,
        "candidate_distribution": candidate_distribution,
        "baseline_distribution": baseline_distribution,
        "mean_latency_ms": round(mean_latency, 3),
        "gates": gates,
        "blockers": blockers,
        "thresholds": {
            "minimum_shadow_samples": MIN_SHADOW_SAMPLES,
            "minimum_macro_precision": MIN_MACRO_PRECISION,
            "minimum_macro_recall": MIN_MACRO_RECALL,
            "maximum_multiclass_brier": MAX_BRIER,
            "maximum_expected_calibration_error": MAX_ECE,
            "maximum_class_distribution_psi": MAX_CLASS_DISTRIBUTION_PSI,
        },
    }


def rollback_decision(metrics: dict[str, Any]) -> dict[str, Any]:
    candidate = metrics.get("candidate") if isinstance(metrics.get("candidate"), dict) else {}
    conditions = {
        "recall": float(candidate.get("macro_recall") or 0.0) < ROLLBACK_MIN_MACRO_RECALL,
        "brier": float(candidate.get("multiclass_brier") if candidate.get("multiclass_brier") is not None else 1.0) > ROLLBACK_MAX_BRIER,
        "calibration": float(candidate.get("expected_calibration_error") if candidate.get("expected_calibration_error") is not None else 1.0) > ROLLBACK_MAX_ECE,
        "drift": float(metrics.get("population_stability_index") or 0.0) > ROLLBACK_MAX_PSI,
        "latency": float(metrics.get("mean_latency_ms") or 0.0) > ROLLBACK_MAX_LATENCY_MS,
    }
    reasons = [name for name, triggered in conditions.items() if triggered]
    return {
        "rollback": bool(reasons),
        "reasons": reasons,
        "fallback": "ithute-mail-intelligence-v1",
        "thresholds": {
            "minimum_macro_recall": ROLLBACK_MIN_MACRO_RECALL,
            "maximum_multiclass_brier": ROLLBACK_MAX_BRIER,
            "maximum_expected_calibration_error": ROLLBACK_MAX_ECE,
            "maximum_population_stability_index": ROLLBACK_MAX_PSI,
            "maximum_latency_ms": ROLLBACK_MAX_LATENCY_MS,
        },
    }


def shadow_policy() -> dict[str, Any]:
    return {
        "minimum_shadow_samples": MIN_SHADOW_SAMPLES,
        "canary_fraction": 0.05,
        "direct_activation_allowed": False,
        "fallback": "ithute-mail-intelligence-v1",
        "automatic_rollback": rollback_decision({
            "candidate": {
                "macro_recall": 1.0,
                "multiclass_brier": 0.0,
                "expected_calibration_error": 0.0,
            },
            "population_stability_index": 0.0,
            "mean_latency_ms": 0.0,
        })["thresholds"],
    }
