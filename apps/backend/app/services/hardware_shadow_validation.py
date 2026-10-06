from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any, Iterable

from app.services.hardware_model_evaluation import classification_metrics

MIN_SHADOW_SAMPLES = 50
MIN_SHADOW_PRECISION = 0.82
MIN_SHADOW_RECALL = 0.72
MAX_SHADOW_FPR = 0.12
MAX_SHADOW_BRIER = 0.18
MAX_EXPECTED_CALIBRATION_ERROR = 0.10
MAX_POPULATION_STABILITY_INDEX = 0.20
MAX_MEAN_PROBABILITY_DRIFT = 0.15
PAGE_HINKLEY_DELTA = 0.005
PAGE_HINKLEY_THRESHOLD = 0.20

CANARY_FRACTION = 0.05
ROLLBACK_MIN_RECALL = 0.65
ROLLBACK_MAX_FPR = 0.20
ROLLBACK_MAX_ECE = 0.15
ROLLBACK_MAX_PSI = 0.25
ROLLBACK_MAX_LATENCY_MS = 250.0


def _prob(value: Any) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError("probability must be finite")
    return max(0.0, min(1.0, number))


def expected_calibration_error(
    rows: Iterable[dict[str, Any]],
    *,
    probability_key: str = "candidate_probability",
    bins: int = 10,
) -> float:
    data = list(rows)
    if not data:
        return 1.0
    bins = max(2, int(bins))
    error = 0.0
    for idx in range(bins):
        lower = idx / bins
        upper = (idx + 1) / bins
        bucket = []
        for row in data:
            p = _prob(row[probability_key])
            if lower <= p < upper or (idx == bins - 1 and p == 1.0):
                bucket.append((p, int(row.get("target") or 0)))
        if not bucket:
            continue
        confidence = mean(p for p, _ in bucket)
        accuracy = mean(target for _, target in bucket)
        error += (len(bucket) / len(data)) * abs(confidence - accuracy)
    return round(error, 6)


def population_stability_index(reference: Iterable[float], current: Iterable[float], *, bins: int = 10) -> float:
    ref = [_prob(value) for value in reference]
    cur = [_prob(value) for value in current]
    if not ref or not cur:
        return 1.0
    bins = max(2, int(bins))
    epsilon = 1e-6
    score = 0.0
    for idx in range(bins):
        lower = idx / bins
        upper = (idx + 1) / bins
        ref_count = sum(1 for p in ref if lower <= p < upper or (idx == bins - 1 and p == 1.0))
        cur_count = sum(1 for p in cur if lower <= p < upper or (idx == bins - 1 and p == 1.0))
        ref_share = max(ref_count / len(ref), epsilon)
        cur_share = max(cur_count / len(cur), epsilon)
        from math import log
        score += (cur_share - ref_share) * log(cur_share / ref_share)
    return round(score, 6)


def page_hinkley_change(
    values: Iterable[float],
    *,
    delta: float = PAGE_HINKLEY_DELTA,
    threshold: float = PAGE_HINKLEY_THRESHOLD,
) -> dict[str, Any]:
    series = [float(value) for value in values]
    if len(series) < 5:
        return {"change_detected": False, "score": 0.0, "samples": len(series)}
    running_mean = 0.0
    cumulative = 0.0
    minimum = 0.0
    max_excursion = 0.0
    for index, value in enumerate(series, start=1):
        running_mean += (value - running_mean) / index
        cumulative += value - running_mean - delta
        minimum = min(minimum, cumulative)
        max_excursion = max(max_excursion, cumulative - minimum)
    return {
        "change_detected": max_excursion > threshold,
        "score": round(max_excursion, 6),
        "samples": len(series),
        "threshold": threshold,
    }


def shadow_validation(
    rows: Iterable[dict[str, Any]],
    *,
    reference_probabilities: Iterable[float] | None = None,
) -> dict[str, Any]:
    data = list(rows)
    candidate = classification_metrics(data, probability_key="candidate_probability")
    baseline = classification_metrics(data, probability_key="baseline_probability")
    ece = expected_calibration_error(data)

    current_probabilities = [_prob(row["candidate_probability"]) for row in data]
    reference = list(reference_probabilities or [row["baseline_probability"] for row in data])
    psi = population_stability_index(reference, current_probabilities)
    drift = abs((mean(current_probabilities) if current_probabilities else 0.0) - (mean([_prob(v) for v in reference]) if reference else 0.0))
    residuals = [
        abs(_prob(row["candidate_probability"]) - int(row.get("target") or 0))
        for row in data
    ]
    page_hinkley = page_hinkley_change(residuals)

    gates = {
        "sample_count": candidate["sample_count"] >= MIN_SHADOW_SAMPLES,
        "precision": candidate["precision"] >= MIN_SHADOW_PRECISION,
        "recall": candidate["recall"] >= MIN_SHADOW_RECALL,
        "false_positive_rate": candidate["false_positive_rate"] <= MAX_SHADOW_FPR,
        "brier_score": candidate["brier_score"] <= MAX_SHADOW_BRIER,
        "calibration": ece <= MAX_EXPECTED_CALIBRATION_ERROR,
        "population_drift": psi <= MAX_POPULATION_STABILITY_INDEX,
        "mean_probability_drift": drift <= MAX_MEAN_PROBABILITY_DRIFT,
        "change_point": not page_hinkley["change_detected"],
        "f1_no_regression": candidate["f1"] >= baseline["f1"],
        "brier_no_regression": candidate["brier_score"] <= baseline["brier_score"],
    }

    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "candidate": candidate,
        "baseline": baseline,
        "expected_calibration_error": round(ece, 6),
        "population_stability_index": round(psi, 6),
        "mean_probability_drift": round(drift, 6),
        "page_hinkley": page_hinkley,
        "gates": gates,
        "blockers": blockers,
        "eligible_for_canary": all(gates.values()),
        "canary_fraction": CANARY_FRACTION if all(gates.values()) else 0.0,
    }


def rollback_decision(
    live_metrics: dict[str, Any],
    *,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if float(live_metrics.get("recall") or 0.0) < ROLLBACK_MIN_RECALL:
        reasons.append("recall_below_floor")
    if float(live_metrics.get("false_positive_rate") or 1.0) > ROLLBACK_MAX_FPR:
        reasons.append("false_positive_rate_above_limit")
    if float(live_metrics.get("expected_calibration_error") or 1.0) > ROLLBACK_MAX_ECE:
        reasons.append("calibration_error_above_limit")
    if float(live_metrics.get("population_stability_index") or 1.0) > ROLLBACK_MAX_PSI:
        reasons.append("population_drift_above_limit")
    if latency_ms is not None and float(latency_ms) > ROLLBACK_MAX_LATENCY_MS:
        reasons.append("latency_above_limit")
    return {
        "rollback_required": bool(reasons),
        "reasons": reasons,
        "fallback": "robust_ensemble_baseline",
    }


def shadow_policy() -> dict[str, Any]:
    return {
        "lifecycle": ["candidate", "shadow", "qualified", "canary", "active", "retired_or_rolled_back"],
        "algorithms": [
            "classification_metrics",
            "expected_calibration_error",
            "population_stability_index",
            "page_hinkley_change_detection",
        ],
        "minimum_shadow_samples": MIN_SHADOW_SAMPLES,
        "minimum_precision": MIN_SHADOW_PRECISION,
        "minimum_recall": MIN_SHADOW_RECALL,
        "maximum_false_positive_rate": MAX_SHADOW_FPR,
        "maximum_brier_score": MAX_SHADOW_BRIER,
        "maximum_expected_calibration_error": MAX_EXPECTED_CALIBRATION_ERROR,
        "maximum_population_stability_index": MAX_POPULATION_STABILITY_INDEX,
        "maximum_mean_probability_drift": MAX_MEAN_PROBABILITY_DRIFT,
        "canary_fraction": CANARY_FRACTION,
        "automatic_rollback": {
            "minimum_recall": ROLLBACK_MIN_RECALL,
            "maximum_false_positive_rate": ROLLBACK_MAX_FPR,
            "maximum_expected_calibration_error": ROLLBACK_MAX_ECE,
            "maximum_population_stability_index": ROLLBACK_MAX_PSI,
            "maximum_latency_ms": ROLLBACK_MAX_LATENCY_MS,
            "fallback": "robust_ensemble_baseline",
        },
    }
