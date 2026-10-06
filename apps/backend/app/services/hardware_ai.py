from __future__ import annotations

import math
import random
from statistics import median
from typing import Any, Sequence


FEATURES = (
    "temperature_celsius",
    "memory_pressure_avg10",
    "io_pressure_avg10",
    "filesystem_used_percent",
    "cpu_iowait_percent",
    "cpu_steal_percent",
    "block_io_ms_per_op",
    "block_weighted_ms_per_op",
    "media_error_delta",
    "network_error_delta",
    "tcp_retrans_delta",
    "ebpf_inflight_delta",
    "ebpf_oom_delta",
    "ebpf_block_p50_ms",
    "ebpf_block_p95_ms",
    "ebpf_block_p99_ms",
    "ecc_corrected_delta",
    "ecc_uncorrected_delta",
)

MIN_MODEL_SAMPLES = 24
ISOLATION_TREES = 48
ISOLATION_SAMPLE_SIZE = 64
SEED = 20261006


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mad(values: Sequence[float], centre: float) -> float:
    return median([abs(value - centre) for value in values]) if values else 0.0


def _feature_columns(history: Sequence[Any], current: Any) -> tuple[list[str], dict[str, float], list[list[float]], list[float]]:
    names: list[str] = []
    medians: dict[str, float] = {}
    for name in FEATURES:
        current_value = _finite(getattr(current, name, None))
        values = [_finite(getattr(point, name, None)) for point in history]
        clean = [value for value in values if value is not None]
        if current_value is None or len(clean) < MIN_MODEL_SAMPLES:
            continue
        names.append(name)
        medians[name] = median(clean)

    matrix: list[list[float]] = []
    for point in history:
        row = []
        for name in names:
            value = _finite(getattr(point, name, None))
            row.append(medians[name] if value is None else value)
        matrix.append(row)

    current_row = [
        medians[name] if _finite(getattr(current, name, None)) is None else float(getattr(current, name))
        for name in names
    ]
    return names, medians, matrix, current_row


def _c_factor(size: int) -> float:
    if size <= 1:
        return 0.0
    if size == 2:
        return 1.0
    harmonic = sum(1.0 / index for index in range(1, size))
    return 2.0 * harmonic - 2.0 * (size - 1) / size


def _build_tree(rows: list[list[float]], depth: int, max_depth: int, rng: random.Random):
    if depth >= max_depth or len(rows) <= 1:
        return ("leaf", len(rows))

    width = len(rows[0]) if rows else 0
    viable: list[tuple[int, float, float]] = []
    for feature in range(width):
        values = [row[feature] for row in rows]
        lo, hi = min(values), max(values)
        if hi > lo:
            viable.append((feature, lo, hi))
    if not viable:
        return ("leaf", len(rows))

    feature, lo, hi = rng.choice(viable)
    split = rng.uniform(lo, hi)
    left = [row for row in rows if row[feature] < split]
    right = [row for row in rows if row[feature] >= split]
    if not left or not right:
        return ("leaf", len(rows))
    return (
        "node",
        feature,
        split,
        _build_tree(left, depth + 1, max_depth, rng),
        _build_tree(right, depth + 1, max_depth, rng),
    )


def _path_length(tree, row: list[float], depth: int = 0) -> float:
    if tree[0] == "leaf":
        size = int(tree[1])
        return depth + (_c_factor(size) if size > 1 else 0.0)
    _, feature, split, left, right = tree
    return _path_length(left if row[feature] < split else right, row, depth + 1)


def isolation_forest_signal(history: Sequence[Any], current: Any) -> dict[str, Any]:
    names, _, matrix, current_row = _feature_columns(history, current)
    if len(matrix) < MIN_MODEL_SAMPLES or not names:
        return {"ready": False, "risk_score": 0, "anomaly_score": 0.0, "features": len(names)}

    sample_size = min(ISOLATION_SAMPLE_SIZE, len(matrix))
    max_depth = max(1, math.ceil(math.log2(sample_size)))
    paths: list[float] = []
    for tree_index in range(ISOLATION_TREES):
        rng = random.Random(SEED + tree_index)
        indices = rng.sample(range(len(matrix)), sample_size)
        rows = [matrix[index] for index in indices]
        tree = _build_tree(rows, 0, max_depth, rng)
        paths.append(_path_length(tree, current_row))

    average_path = sum(paths) / len(paths)
    normalizer = max(_c_factor(sample_size), 1e-6)
    anomaly_score = 2.0 ** (-average_path / normalizer)
    # Classical isolation scores near 0.5 are normal. We deliberately require
    # a strong isolation signal before it contributes material incident risk.
    risk = max(0.0, min(100.0, (anomaly_score - 0.50) / 0.25 * 100.0))
    return {
        "ready": True,
        "risk_score": round(risk, 1),
        "anomaly_score": round(anomaly_score, 4),
        "features": len(names),
        "trees": ISOLATION_TREES,
    }


def change_point_signal(history: Sequence[Any], current: Any) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for name in FEATURES:
        values = [_finite(getattr(point, name, None)) for point in history]
        clean = [value for value in values if value is not None]
        current_value = _finite(getattr(current, name, None))
        if current_value is None or len(clean) < MIN_MODEL_SAMPLES:
            continue

        cut = max(12, int(len(clean) * 0.75))
        baseline = clean[:cut]
        recent = clean[cut:] + [current_value]
        if len(baseline) < 12 or len(recent) < 2:
            continue

        base_median = median(baseline)
        recent_median = median(recent)
        scale = max(0.25, 1.4826 * _mad(baseline, base_median))
        shift = max(0.0, (recent_median - base_median) / scale)
        risk = min(100.0, max(0.0, shift - 1.0) * 25.0)
        candidate = {
            "metric": name,
            "risk_score": round(risk, 1),
            "shift_sigma": round(shift, 3),
            "baseline_median": round(base_median, 4),
            "recent_median": round(recent_median, 4),
        }
        if best is None or candidate["risk_score"] > best["risk_score"]:
            best = candidate

    if best is None:
        return {"ready": False, "risk_score": 0}
    return {"ready": True, **best}


def weibull_survival_projection(risk_score: float, confidence: float) -> dict[str, Any]:
    risk = max(0.0, min(100.0, float(risk_score)))
    confidence = max(0.0, min(1.0, float(confidence)))
    if risk < 50 or confidence < 0.5:
        return {
            "ready": False,
            "calibration": "prior_only",
            "reason": "Risk/confidence is too low for a useful failure-horizon estimate",
        }

    # Conservative prior-only Weibull projection. It is displayed as decision
    # support but is never used to trigger destructive automation. Once Ithute
    # accumulates confirmed failure labels these parameters can be calibrated.
    shape = 1.6
    severity = risk / 100.0
    scale_hours = max(12.0, 24.0 + (1.0 - severity) ** 2 * 696.0)
    median_hours = scale_hours * (math.log(2.0) ** (1.0 / shape))
    survival_72h = math.exp(-((72.0 / scale_hours) ** shape))
    return {
        "ready": True,
        "calibration": "prior_only",
        "shape": shape,
        "scale_hours": round(scale_hours, 1),
        "median_risk_horizon_hours": round(median_hours, 1),
        "failure_probability_72h": round((1.0 - survival_72h) * 100.0, 1),
    }


def ensemble_signals(history: Sequence[Any], current: Any, baseline_risk: float, confidence: float) -> dict[str, Any]:
    isolation = isolation_forest_signal(history, current)
    change = change_point_signal(history, current)

    baseline = max(0.0, min(100.0, float(baseline_risk)))
    weighted = baseline * 0.60
    weight_total = 0.60
    ai_strong_votes = 0
    if isolation.get("ready"):
        isolation_risk = float(isolation["risk_score"])
        weighted += isolation_risk * 0.25
        weight_total += 0.25
        ai_strong_votes += 1 if isolation_risk >= 75.0 else 0
    if change.get("ready"):
        change_risk = float(change["risk_score"])
        weighted += change_risk * 0.15
        weight_total += 0.15
        ai_strong_votes += 1 if change_risk >= 75.0 else 0

    corroborated = weighted / max(weight_total, 1e-6)
    # The established robust detector is the safety floor: new AI can
    # corroborate or raise risk, but never suppress a proven strong signal.
    ensemble = max(baseline, corroborated)

    # Auxiliary AI may not promote a sub-high robust baseline into high risk
    # unless two independent AI detectors agree strongly.
    if baseline < 75.0 and ensemble >= 75.0 and ai_strong_votes < 2:
        ensemble = 74.0

    survival = weibull_survival_projection(ensemble, confidence)
    return {
        "ensemble_risk_score": int(round(max(0.0, min(100.0, ensemble)))),
        "isolation_forest": isolation,
        "change_point": change,
        "survival": survival,
        "supervised_boosting": {
            "ready": False,
            "engine": "xgboost-compatible",
            "reason": "Waiting for sufficient confirmed hardware failure labels",
        },
    }
