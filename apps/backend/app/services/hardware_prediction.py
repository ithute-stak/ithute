from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Iterable, Sequence


MIN_BASELINE_SAMPLES = 24
TARGET_BASELINE_SAMPLES = 96
EPSILON = 1e-6


@dataclass(frozen=True)
class MetricPoint:
    temperature_celsius: float | None = None
    memory_pressure_avg10: float | None = None
    io_pressure_avg10: float | None = None
    filesystem_used_percent: float | None = None


@dataclass(frozen=True)
class BaselineMetric:
    name: str
    label: str
    median: float
    mad: float
    current: float
    robust_z: float
    slope_per_sample: float
    risk: float


def _clean(values: Iterable[float | None]) -> list[float]:
    result: list[float] = []
    for value in values:
        if value is None:
            continue
        value = float(value)
        if isfinite(value):
            result.append(value)
    return result


def _mad(values: Sequence[float], centre: float) -> float:
    return median([abs(value - centre) for value in values]) if values else 0.0


def _slope(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(n))
    return numerator / denominator if denominator > 0 else 0.0


def _metric(
    name: str,
    label: str,
    history: Sequence[float | None],
    current: float | None,
    *,
    minimum_scale: float,
    slope_scale: float,
) -> BaselineMetric | None:
    values = _clean(history)
    if current is None or not isfinite(float(current)) or len(values) < MIN_BASELINE_SAMPLES:
        return None

    current_value = float(current)
    centre = median(values)
    mad = _mad(values, centre)
    # 1.4826 makes MAD comparable to standard deviation for normally
    # distributed data. A floor prevents a perfectly stable baseline from
    # turning tiny measurement noise into an enormous anomaly.
    scale = max(minimum_scale, 1.4826 * mad)
    robust_z = max(0.0, (current_value - centre) / scale)

    recent = values[-min(24, len(values)) :]
    slope = _slope(recent)

    deviation_risk = min(70.0, max(0.0, robust_z - 1.5) * 20.0)
    trend_risk = min(30.0, max(0.0, slope) / max(slope_scale, EPSILON) * 10.0)
    risk = min(100.0, deviation_risk + trend_risk)

    return BaselineMetric(
        name=name,
        label=label,
        median=centre,
        mad=mad,
        current=current_value,
        robust_z=robust_z,
        slope_per_sample=slope,
        risk=risk,
    )


def predict_hardware_drift(
    history: Sequence[MetricPoint],
    current: MetricPoint,
) -> dict:
    sample_count = len(history)
    if sample_count < MIN_BASELINE_SAMPLES:
        return {
            "state": "learning",
            "risk_score": 0,
            "confidence": min(0.99, sample_count / MIN_BASELINE_SAMPLES),
            "sample_count": sample_count,
            "evidence": [
                f"Learning this server baseline: {sample_count}/{MIN_BASELINE_SAMPLES} minimum samples collected"
            ],
            "metrics": [],
        }

    metrics = [
        _metric(
            "temperature_celsius",
            "temperature",
            [point.temperature_celsius for point in history],
            current.temperature_celsius,
            minimum_scale=1.5,
            slope_scale=0.20,
        ),
        _metric(
            "memory_pressure_avg10",
            "memory pressure",
            [point.memory_pressure_avg10 for point in history],
            current.memory_pressure_avg10,
            minimum_scale=0.5,
            slope_scale=0.15,
        ),
        _metric(
            "io_pressure_avg10",
            "I/O pressure",
            [point.io_pressure_avg10 for point in history],
            current.io_pressure_avg10,
            minimum_scale=0.5,
            slope_scale=0.15,
        ),
        _metric(
            "filesystem_used_percent",
            "filesystem usage",
            [point.filesystem_used_percent for point in history],
            current.filesystem_used_percent,
            minimum_scale=0.5,
            slope_scale=0.05,
        ),
    ]
    available = [metric for metric in metrics if metric is not None]
    if not available:
        return {
            "state": "learning",
            "risk_score": 0,
            "confidence": 0.0,
            "sample_count": sample_count,
            "evidence": ["Baseline samples exist, but comparable predictive signals are not yet available"],
            "metrics": [],
        }

    ranked = sorted(available, key=lambda item: item.risk, reverse=True)
    # The strongest anomalous signal dominates, while a second independent
    # signal raises confidence without allowing many weak metrics to inflate
    # the score uncontrollably.
    risk_score = ranked[0].risk
    if len(ranked) > 1:
        risk_score = min(100.0, risk_score + ranked[1].risk * 0.25)

    confidence = min(1.0, sample_count / TARGET_BASELINE_SAMPLES)
    risk_score = round(risk_score * (0.65 + 0.35 * confidence))

    if risk_score >= 75:
        state = "high"
    elif risk_score >= 50:
        state = "elevated"
    elif risk_score >= 25:
        state = "watch"
    else:
        state = "stable"

    evidence: list[str] = []
    for metric in ranked:
        if metric.risk < 20:
            continue
        parts = [
            f"{metric.label} {metric.current:.1f} vs baseline {metric.median:.1f}",
            f"{metric.robust_z:.1f} robust deviations above normal",
        ]
        if metric.slope_per_sample > 0:
            parts.append(f"rising {metric.slope_per_sample:.2f} per sample")
        evidence.append("; ".join(parts))

    if not evidence:
        evidence.append("Current hardware signals remain close to this server's learned baseline")

    return {
        "state": state,
        "risk_score": int(risk_score),
        "confidence": round(confidence, 3),
        "sample_count": sample_count,
        "evidence": evidence[:8],
        "metrics": [
            {
                "name": metric.name,
                "label": metric.label,
                "baseline_median": round(metric.median, 4),
                "baseline_mad": round(metric.mad, 4),
                "current": round(metric.current, 4),
                "robust_z": round(metric.robust_z, 4),
                "slope_per_sample": round(metric.slope_per_sample, 6),
                "risk": round(metric.risk, 2),
            }
            for metric in ranked
        ],
    }
