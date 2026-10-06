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
    cpu_iowait_percent: float | None = None
    cpu_steal_percent: float | None = None
    block_io_ms_per_op: float | None = None
    block_weighted_ms_per_op: float | None = None
    media_error_delta: float | None = None
    network_error_delta: float | None = None
    tcp_retrans_delta: float | None = None
    ebpf_inflight_delta: float | None = None
    ebpf_oom_delta: float | None = None
    ebpf_block_p50_ms: float | None = None
    ebpf_block_p95_ms: float | None = None
    ebpf_block_p99_ms: float | None = None
    ecc_corrected_delta: float | None = None
    ecc_uncorrected_delta: float | None = None


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



def _counter_delta(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None or not isfinite(previous) or not isfinite(current):
        return None
    delta = current - previous
    return delta if delta >= 0 else None


def _mapping_number(payload: dict, section: str, key: str) -> float | None:
    container = payload.get(section)
    if not isinstance(container, dict):
        return None
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _media_errors(payload: dict) -> dict[str, float]:
    result: dict[str, float] = {}
    devices = payload.get("storage_devices")
    if not isinstance(devices, list):
        return result
    for item in devices[:64]:
        if not isinstance(item, dict):
            continue
        device = item.get("device")
        value = item.get("media_errors")
        if not isinstance(device, str) or not device or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if numeric >= 0 and isfinite(numeric):
            result[device] = numeric
    return result


LATENCY_BUCKET_UPPER_MS = [
    0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0,
    32.0, 64.0, 128.0, 256.0, 512.0, 1000.0, 2000.0, 2000.0,
]


def _histogram(payload: dict) -> list[float] | None:
    ebpf = payload.get("ebpf")
    if not isinstance(ebpf, dict):
        return None
    raw = ebpf.get("block_latency_histogram")
    if not isinstance(raw, list) or len(raw) != len(LATENCY_BUCKET_UPPER_MS):
        return None
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        value = float(item)
        if not isfinite(value) or value < 0:
            return None
        values.append(value)
    return values


def _histogram_percentile(previous_payload: dict, current_payload: dict, percentile: float) -> float | None:
    previous = _histogram(previous_payload)
    current = _histogram(current_payload)
    if previous is None or current is None:
        return None
    delta: list[float] = []
    for old, new in zip(previous, current):
        if new < old:
            return None
        delta.append(new - old)
    total = sum(delta)
    if total <= 0:
        return None
    target = total * percentile
    running = 0.0
    for count, upper_ms in zip(delta, LATENCY_BUCKET_UPPER_MS):
        running += count
        if running >= target:
            return upper_ms
    return LATENCY_BUCKET_UPPER_MS[-1]


def derive_rate_features(previous_payload: dict | None, current_payload: dict | None) -> dict[str, float | None]:
    if not isinstance(previous_payload, dict) or not isinstance(current_payload, dict):
        return {
            "cpu_iowait_percent": None,
            "cpu_steal_percent": None,
            "block_io_ms_per_op": None,
            "block_weighted_ms_per_op": None,
            "media_error_delta": None,
            "network_error_delta": None,
            "tcp_retrans_delta": None,
            "ebpf_inflight_delta": None,
            "ebpf_oom_delta": None,
            "ebpf_block_p50_ms": None,
            "ebpf_block_p95_ms": None,
            "ebpf_block_p99_ms": None,
            "ecc_corrected_delta": None,
            "ecc_uncorrected_delta": None,
        }

    cpu_keys = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
    deltas: dict[str, float] = {}
    for key in cpu_keys:
        delta = _counter_delta(
            _mapping_number(previous_payload, "cpu", key),
            _mapping_number(current_payload, "cpu", key),
        )
        if delta is None:
            deltas = {}
            break
        deltas[key] = delta

    cpu_total = sum(deltas.values()) if deltas else 0.0
    cpu_iowait_percent = (deltas["iowait"] / cpu_total * 100.0) if cpu_total > 0 else None
    cpu_steal_percent = (deltas["steal"] / cpu_total * 100.0) if cpu_total > 0 else None

    reads_delta = _counter_delta(
        _mapping_number(previous_payload, "block", "reads_completed"),
        _mapping_number(current_payload, "block", "reads_completed"),
    )
    writes_delta = _counter_delta(
        _mapping_number(previous_payload, "block", "writes_completed"),
        _mapping_number(current_payload, "block", "writes_completed"),
    )
    io_ms_delta = _counter_delta(
        _mapping_number(previous_payload, "block", "io_ms"),
        _mapping_number(current_payload, "block", "io_ms"),
    )
    weighted_ms_delta = _counter_delta(
        _mapping_number(previous_payload, "block", "weighted_io_ms"),
        _mapping_number(current_payload, "block", "weighted_io_ms"),
    )
    ops_delta = (reads_delta + writes_delta) if reads_delta is not None and writes_delta is not None else None
    block_io_ms_per_op = (io_ms_delta / ops_delta) if io_ms_delta is not None and ops_delta and ops_delta > 0 else None
    block_weighted_ms_per_op = (weighted_ms_delta / ops_delta) if weighted_ms_delta is not None and ops_delta and ops_delta > 0 else None

    previous_media = _media_errors(previous_payload)
    current_media = _media_errors(current_payload)
    media_error_delta = 0.0
    comparable = False
    for device, current_value in current_media.items():
        previous_value = previous_media.get(device)
        if previous_value is None:
            continue
        delta = _counter_delta(previous_value, current_value)
        if delta is None:
            continue
        comparable = True
        media_error_delta += delta

    network_error_delta = 0.0
    network_comparable = False
    for key in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped"):
        delta = _counter_delta(
            _mapping_number(previous_payload, "network", key),
            _mapping_number(current_payload, "network", key),
        )
        if delta is None:
            continue
        network_comparable = True
        network_error_delta += delta

    tcp_retrans_delta = _counter_delta(
        _mapping_number(previous_payload, "network", "tcp_retrans_segs"),
        _mapping_number(current_payload, "network", "tcp_retrans_segs"),
    )

    previous_issued = _mapping_number(previous_payload, "ebpf", "block_requests_issued")
    current_issued = _mapping_number(current_payload, "ebpf", "block_requests_issued")
    previous_completed = _mapping_number(previous_payload, "ebpf", "block_requests_completed")
    current_completed = _mapping_number(current_payload, "ebpf", "block_requests_completed")
    issued_delta = _counter_delta(previous_issued, current_issued)
    completed_delta = _counter_delta(previous_completed, current_completed)
    ebpf_inflight_delta = None
    if issued_delta is not None and completed_delta is not None:
        ebpf_inflight_delta = max(0.0, issued_delta - completed_delta)

    ebpf_oom_delta = _counter_delta(
        _mapping_number(previous_payload, "ebpf", "oom_victims"),
        _mapping_number(current_payload, "ebpf", "oom_victims"),
    )

    ebpf_block_p50_ms = _histogram_percentile(previous_payload, current_payload, 0.50)
    ebpf_block_p95_ms = _histogram_percentile(previous_payload, current_payload, 0.95)
    ebpf_block_p99_ms = _histogram_percentile(previous_payload, current_payload, 0.99)

    ecc_corrected_delta = _counter_delta(
        _mapping_number(previous_payload, "memory_reliability", "corrected_errors"),
        _mapping_number(current_payload, "memory_reliability", "corrected_errors"),
    )
    ecc_uncorrected_delta = _counter_delta(
        _mapping_number(previous_payload, "memory_reliability", "uncorrected_errors"),
        _mapping_number(current_payload, "memory_reliability", "uncorrected_errors"),
    )

    return {
        "cpu_iowait_percent": cpu_iowait_percent,
        "cpu_steal_percent": cpu_steal_percent,
        "block_io_ms_per_op": block_io_ms_per_op,
        "block_weighted_ms_per_op": block_weighted_ms_per_op,
        "media_error_delta": media_error_delta if comparable else None,
        "network_error_delta": network_error_delta if network_comparable else None,
        "tcp_retrans_delta": tcp_retrans_delta,
        "ebpf_inflight_delta": ebpf_inflight_delta,
        "ebpf_oom_delta": ebpf_oom_delta,
        "ebpf_block_p50_ms": ebpf_block_p50_ms,
        "ebpf_block_p95_ms": ebpf_block_p95_ms,
        "ebpf_block_p99_ms": ebpf_block_p99_ms,
        "ecc_corrected_delta": ecc_corrected_delta,
        "ecc_uncorrected_delta": ecc_uncorrected_delta,
    }


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
        _metric(
            "cpu_iowait_percent",
            "CPU iowait",
            [point.cpu_iowait_percent for point in history],
            current.cpu_iowait_percent,
            minimum_scale=0.5,
            slope_scale=0.10,
        ),
        _metric(
            "cpu_steal_percent",
            "CPU steal",
            [point.cpu_steal_percent for point in history],
            current.cpu_steal_percent,
            minimum_scale=0.25,
            slope_scale=0.05,
        ),
        _metric(
            "block_io_ms_per_op",
            "block I/O busy-time proxy",
            [point.block_io_ms_per_op for point in history],
            current.block_io_ms_per_op,
            minimum_scale=0.5,
            slope_scale=0.10,
        ),
        _metric(
            "block_weighted_ms_per_op",
            "block queue-time proxy",
            [point.block_weighted_ms_per_op for point in history],
            current.block_weighted_ms_per_op,
            minimum_scale=0.75,
            slope_scale=0.15,
        ),
        _metric(
            "media_error_delta",
            "SMART/NVMe media-error growth",
            [point.media_error_delta for point in history],
            current.media_error_delta,
            minimum_scale=0.25,
            slope_scale=0.05,
        ),
        _metric(
            "network_error_delta",
            "network error/drop growth",
            [point.network_error_delta for point in history],
            current.network_error_delta,
            minimum_scale=1.0,
            slope_scale=0.20,
        ),
        _metric(
            "tcp_retrans_delta",
            "TCP retransmission growth",
            [point.tcp_retrans_delta for point in history],
            current.tcp_retrans_delta,
            minimum_scale=2.0,
            slope_scale=0.50,
        ),
        _metric(
            "ebpf_inflight_delta",
            "eBPF block request backlog growth",
            [point.ebpf_inflight_delta for point in history],
            current.ebpf_inflight_delta,
            minimum_scale=2.0,
            slope_scale=0.50,
        ),
        _metric(
            "ebpf_oom_delta",
            "eBPF OOM victim growth",
            [point.ebpf_oom_delta for point in history],
            current.ebpf_oom_delta,
            minimum_scale=0.25,
            slope_scale=0.05,
        ),
        _metric(
            "ebpf_block_p50_ms",
            "eBPF block latency p50",
            [point.ebpf_block_p50_ms for point in history],
            current.ebpf_block_p50_ms,
            minimum_scale=0.25,
            slope_scale=0.05,
        ),
        _metric(
            "ebpf_block_p95_ms",
            "eBPF block latency p95",
            [point.ebpf_block_p95_ms for point in history],
            current.ebpf_block_p95_ms,
            minimum_scale=0.5,
            slope_scale=0.10,
        ),
        _metric(
            "ebpf_block_p99_ms",
            "eBPF block latency p99",
            [point.ebpf_block_p99_ms for point in history],
            current.ebpf_block_p99_ms,
            minimum_scale=1.0,
            slope_scale=0.20,
        ),
        _metric(
            "ecc_corrected_delta",
            "ECC corrected-error growth",
            [point.ecc_corrected_delta for point in history],
            current.ecc_corrected_delta,
            minimum_scale=0.25,
            slope_scale=0.05,
        ),
        _metric(
            "ecc_uncorrected_delta",
            "ECC uncorrected-error growth",
            [point.ecc_uncorrected_delta for point in history],
            current.ecc_uncorrected_delta,
            minimum_scale=0.10,
            slope_scale=0.02,
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
