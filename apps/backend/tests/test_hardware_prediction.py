from app.services.hardware_prediction import MetricPoint, predict_hardware_drift


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
