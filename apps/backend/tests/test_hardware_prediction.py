from app.services.hardware_ai import change_point_signal, ensemble_signals, isolation_forest_signal, weibull_survival_projection
from app.services.hardware_prediction import MetricPoint, derive_rate_features, predict_hardware_drift


def _point(temp=45.0, memory=1.0, io=1.0, disk=50.0):
    return MetricPoint(
        temperature_celsius=temp,
        memory_pressure_avg10=memory,
        io_pressure_avg10=io,
        filesystem_used_percent=disk,
    )


def test_prediction_learns_before_alerting():
    result = predict_hardware_drift([_point()] * 10, _point(temp=80))
    assert result["state"] == "learning"
    assert result["risk_score"] == 0
    assert result["sample_count"] == 10


def test_prediction_stays_stable_near_baseline():
    history = [_point(temp=44 + (i % 3), memory=1 + (i % 2) * 0.2, io=1.5, disk=50 + i * 0.02) for i in range(96)]
    result = predict_hardware_drift(history, _point(temp=46, memory=1.2, io=1.6, disk=52))
    assert result["state"] in {"stable", "watch"}
    assert result["risk_score"] < 50
    assert result["confidence"] == 1.0


def test_prediction_detects_temperature_drift_before_fixed_critical_threshold():
    history = [_point(temp=44 + (i % 4) * 0.3, memory=1, io=1, disk=50) for i in range(96)]
    result = predict_hardware_drift(history, _point(temp=61, memory=1, io=1, disk=50))
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    assert any("temperature" in item for item in result["evidence"])


def test_prediction_uses_multiple_independent_signals():
    history = [_point(temp=45, memory=1, io=1, disk=50) for _ in range(96)]
    result = predict_hardware_drift(history, _point(temp=65, memory=20, io=22, disk=70))
    assert result["state"] == "high"
    assert result["risk_score"] >= 75
    assert len(result["evidence"]) >= 2



def test_counter_delta_features_capture_iowait_steal_and_block_pressure():
    previous = {
        "cpu": {"user": 100, "nice": 0, "system": 40, "idle": 800, "iowait": 10, "irq": 0, "softirq": 5, "steal": 0},
        "block": {"reads_completed": 1000, "writes_completed": 500, "io_ms": 2000, "weighted_io_ms": 2600},
        "storage_devices": [{"device": "/dev/nvme0n1", "media_errors": 2}],
    }
    current = {
        "cpu": {"user": 150, "nice": 0, "system": 60, "idle": 870, "iowait": 30, "irq": 0, "softirq": 10, "steal": 5},
        "block": {"reads_completed": 1030, "writes_completed": 520, "io_ms": 2250, "weighted_io_ms": 3000},
        "storage_devices": [{"device": "/dev/nvme0n1", "media_errors": 3}],
    }
    features = derive_rate_features(previous, current)
    assert features["cpu_iowait_percent"] is not None
    assert features["cpu_iowait_percent"] > 0
    assert features["cpu_steal_percent"] is not None
    assert features["cpu_steal_percent"] > 0
    assert features["block_io_ms_per_op"] == 5.0
    assert features["block_weighted_ms_per_op"] == 8.0
    assert features["media_error_delta"] == 1.0


def test_counter_delta_features_ignore_counter_resets():
    previous = {
        "cpu": {"user": 100, "nice": 0, "system": 10, "idle": 500, "iowait": 20, "irq": 0, "softirq": 0, "steal": 1},
        "block": {"reads_completed": 100, "writes_completed": 50, "io_ms": 1000, "weighted_io_ms": 1200},
        "storage_devices": [{"device": "/dev/nvme0n1", "media_errors": 5}],
    }
    current = {
        "cpu": {"user": 1, "nice": 0, "system": 1, "idle": 5, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        "block": {"reads_completed": 1, "writes_completed": 1, "io_ms": 10, "weighted_io_ms": 10},
        "storage_devices": [{"device": "/dev/nvme0n1", "media_errors": 0}],
    }
    features = derive_rate_features(previous, current)
    assert features["cpu_iowait_percent"] is None
    assert features["cpu_steal_percent"] is None
    assert features["block_io_ms_per_op"] is None
    assert features["block_weighted_ms_per_op"] is None
    assert features["media_error_delta"] is None


def test_prediction_detects_media_error_growth_and_cpu_steal():
    history = [
        MetricPoint(
            temperature_celsius=45,
            memory_pressure_avg10=1,
            io_pressure_avg10=1,
            filesystem_used_percent=50,
            cpu_iowait_percent=0.5,
            cpu_steal_percent=0.2,
            block_io_ms_per_op=1.0,
            block_weighted_ms_per_op=1.5,
            media_error_delta=0,
        )
        for _ in range(96)
    ]
    current = MetricPoint(
        temperature_celsius=45,
        memory_pressure_avg10=1,
        io_pressure_avg10=1,
        filesystem_used_percent=50,
        cpu_iowait_percent=8,
        cpu_steal_percent=6,
        block_io_ms_per_op=6,
        block_weighted_ms_per_op=10,
        media_error_delta=1,
    )
    result = predict_hardware_drift(history, current)
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    labels = " ".join(result["evidence"])
    assert "CPU" in labels or "media-error" in labels or "block" in labels



def test_counter_delta_features_capture_network_fault_growth():
    previous = {
        "cpu": {"user": 10, "nice": 0, "system": 5, "idle": 100, "iowait": 1, "irq": 0, "softirq": 0, "steal": 0},
        "block": {"reads_completed": 10, "writes_completed": 10, "io_ms": 100, "weighted_io_ms": 120},
        "network": {"rx_errors": 1, "tx_errors": 2, "rx_dropped": 3, "tx_dropped": 4, "tcp_retrans_segs": 10},
    }
    current = {
        "cpu": {"user": 20, "nice": 0, "system": 10, "idle": 180, "iowait": 2, "irq": 0, "softirq": 0, "steal": 0},
        "block": {"reads_completed": 20, "writes_completed": 20, "io_ms": 200, "weighted_io_ms": 240},
        "network": {"rx_errors": 3, "tx_errors": 3, "rx_dropped": 8, "tx_dropped": 4, "tcp_retrans_segs": 16},
    }
    features = derive_rate_features(previous, current)
    assert features["network_error_delta"] == 8.0
    assert features["tcp_retrans_delta"] == 6.0


def test_prediction_detects_network_retransmission_drift():
    history = [
        MetricPoint(
            temperature_celsius=45,
            memory_pressure_avg10=1,
            io_pressure_avg10=1,
            filesystem_used_percent=50,
            cpu_iowait_percent=0.5,
            cpu_steal_percent=0.1,
            block_io_ms_per_op=1,
            block_weighted_ms_per_op=1,
            media_error_delta=0,
            network_error_delta=0,
            tcp_retrans_delta=1,
        )
        for _ in range(96)
    ]
    current = MetricPoint(
        temperature_celsius=45,
        memory_pressure_avg10=1,
        io_pressure_avg10=1,
        filesystem_used_percent=50,
        cpu_iowait_percent=0.5,
        cpu_steal_percent=0.1,
        block_io_ms_per_op=1,
        block_weighted_ms_per_op=1,
        media_error_delta=0,
        network_error_delta=20,
        tcp_retrans_delta=40,
    )
    result = predict_hardware_drift(history, current)
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    assert any("network" in item.lower() or "tcp" in item.lower() for item in result["evidence"])



def test_counter_delta_features_capture_ebpf_backlog_and_oom_growth():
    previous = {
        "cpu": {"user": 1, "nice": 0, "system": 1, "idle": 10, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        "block": {"reads_completed": 1, "writes_completed": 1, "io_ms": 1, "weighted_io_ms": 1},
        "ebpf": {"block_requests_issued": 100, "block_requests_completed": 100, "oom_victims": 0},
    }
    current = {
        "cpu": {"user": 2, "nice": 0, "system": 2, "idle": 20, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        "block": {"reads_completed": 2, "writes_completed": 2, "io_ms": 2, "weighted_io_ms": 2},
        "ebpf": {"block_requests_issued": 120, "block_requests_completed": 112, "oom_victims": 1},
    }
    features = derive_rate_features(previous, current)
    assert features["ebpf_inflight_delta"] == 8.0
    assert features["ebpf_oom_delta"] == 1.0


def test_prediction_detects_ebpf_oom_and_block_backlog_growth():
    history = [
        MetricPoint(
            temperature_celsius=45,
            memory_pressure_avg10=1,
            io_pressure_avg10=1,
            filesystem_used_percent=50,
            ebpf_inflight_delta=0,
            ebpf_oom_delta=0,
        )
        for _ in range(96)
    ]
    current = MetricPoint(
        temperature_celsius=45,
        memory_pressure_avg10=1,
        io_pressure_avg10=1,
        filesystem_used_percent=50,
        ebpf_inflight_delta=18,
        ebpf_oom_delta=1,
    )
    result = predict_hardware_drift(history, current)
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    assert any("eBPF" in item or "OOM" in item for item in result["evidence"])



def test_ebpf_latency_histogram_derives_interval_percentiles():
    previous = {
        "ebpf": {
            "block_latency_histogram": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160]
        }
    }
    current = {
        "ebpf": {
            "block_latency_histogram": [10, 20, 30, 40, 50, 60, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170]
        }
    }
    features = derive_rate_features(previous, current)
    assert features["ebpf_block_p50_ms"] is not None
    assert features["ebpf_block_p95_ms"] is not None
    assert features["ebpf_block_p99_ms"] is not None
    assert features["ebpf_block_p50_ms"] <= features["ebpf_block_p95_ms"] <= features["ebpf_block_p99_ms"]


def test_ebpf_latency_histogram_ignores_counter_reset():
    previous = {"ebpf": {"block_latency_histogram": [10] * 16}}
    current = {"ebpf": {"block_latency_histogram": [1] * 16}}
    features = derive_rate_features(previous, current)
    assert features["ebpf_block_p50_ms"] is None
    assert features["ebpf_block_p95_ms"] is None
    assert features["ebpf_block_p99_ms"] is None


def test_prediction_detects_ebpf_p99_latency_drift():
    history = [
        MetricPoint(
            temperature_celsius=45,
            memory_pressure_avg10=1,
            io_pressure_avg10=1,
            filesystem_used_percent=50,
            ebpf_block_p50_ms=0.5,
            ebpf_block_p95_ms=2.0,
            ebpf_block_p99_ms=4.0,
        )
        for _ in range(96)
    ]
    current = MetricPoint(
        temperature_celsius=45,
        memory_pressure_avg10=1,
        io_pressure_avg10=1,
        filesystem_used_percent=50,
        ebpf_block_p50_ms=2.0,
        ebpf_block_p95_ms=32.0,
        ebpf_block_p99_ms=128.0,
    )
    result = predict_hardware_drift(history, current)
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    assert any("latency" in item.lower() for item in result["evidence"])



def test_counter_delta_features_capture_ecc_growth():
    previous = {"memory_reliability": {"corrected_errors": 2, "uncorrected_errors": 0}}
    current = {"memory_reliability": {"corrected_errors": 5, "uncorrected_errors": 1}}
    features = derive_rate_features(previous, current)
    assert features["ecc_corrected_delta"] == 3.0
    assert features["ecc_uncorrected_delta"] == 1.0


def test_prediction_detects_ecc_growth():
    history = [
        MetricPoint(
            temperature_celsius=45,
            memory_pressure_avg10=1,
            io_pressure_avg10=1,
            filesystem_used_percent=50,
            ecc_corrected_delta=0,
            ecc_uncorrected_delta=0,
        )
        for _ in range(96)
    ]
    current = MetricPoint(
        temperature_celsius=45,
        memory_pressure_avg10=1,
        io_pressure_avg10=1,
        filesystem_used_percent=50,
        ecc_corrected_delta=8,
        ecc_uncorrected_delta=1,
    )
    result = predict_hardware_drift(history, current)
    assert result["state"] in {"elevated", "high"}
    assert result["risk_score"] >= 50
    assert any("ECC" in item for item in result["evidence"])



def test_isolation_forest_is_deterministic_and_flags_large_multisignal_anomaly():
    history = [
        _point(temp=44 + (i % 3) * 0.2, memory=1 + (i % 2) * 0.1, io=1.2, disk=50 + i * 0.01)
        for i in range(96)
    ]
    current = _point(temp=88, memory=35, io=40, disk=96)
    first = isolation_forest_signal(history, current)
    second = isolation_forest_signal(history, current)
    assert first == second
    assert first["ready"] is True
    assert first["trees"] == 48
    assert first["risk_score"] >= 35


def test_change_point_detects_sustained_regime_shift():
    history = [_point(temp=45, memory=1, io=1, disk=50) for _ in range(72)]
    history += [_point(temp=64, memory=1, io=1, disk=50) for _ in range(24)]
    result = change_point_signal(history, _point(temp=66, memory=1, io=1, disk=50))
    assert result["ready"] is True
    assert result["metric"] == "temperature_celsius"
    assert result["risk_score"] >= 50


def test_survival_projection_is_guarded_and_prior_only():
    low = weibull_survival_projection(30, 1.0)
    assert low["ready"] is False

    elevated = weibull_survival_projection(80, 1.0)
    assert elevated["ready"] is True
    assert elevated["calibration"] == "prior_only"
    assert 0 < elevated["failure_probability_72h"] <= 100
    assert elevated["median_risk_horizon_hours"] > 0


def test_ai_ensemble_requires_consensus_for_high_risk():
    history = [_point(temp=45, memory=1, io=1, disk=50) for _ in range(96)]
    current = _point(temp=45, memory=1, io=1, disk=50)
    result = ensemble_signals(history, current, baseline_risk=100, confidence=1.0)
    assert result["ensemble_risk_score"] <= 74
    assert result["supervised_boosting"]["ready"] is False


def test_prediction_exposes_independent_model_votes():
    history = [_point(temp=45, memory=1, io=1, disk=50) for _ in range(96)]
    result = predict_hardware_drift(history, _point(temp=80, memory=25, io=30, disk=90))
    assert "models" in result
    assert result["models"]["robust_baseline"]["ready"] is True
    assert result["models"]["isolation_forest"]["ready"] is True
    assert result["models"]["change_point"]["ready"] is True
    assert result["models"]["supervised_boosting"]["engine"] == "xgboost-compatible"
