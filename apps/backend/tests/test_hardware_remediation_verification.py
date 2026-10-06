from app.services.hardware_remediation_verification import verify_remediation


def _sample(**overrides):
    base = {
        "health_score": 60,
        "predictive_risk_score": 80,
        "temperature_celsius": 82,
        "memory_pressure_avg10": 20,
        "io_pressure_avg10": 24,
        "filesystem_used_percent": 88,
        "storage_warning_count": 1,
    }
    base.update(overrides)
    return base


def test_verifier_waits_for_minimum_post_samples():
    result = verify_remediation(_sample(), [_sample(temperature_celsius=70)] * 2, "inspect_cooling_and_thermal_path")
    assert result["ready"] is False
    assert result["outcome"] == ""
    assert result["sample_count"] == 2


def test_verifier_confirms_resolved_cooling_remediation():
    baseline = _sample(health_score=55, predictive_risk_score=88, temperature_celsius=90)
    posts = [
        _sample(health_score=88, predictive_risk_score=30, temperature_celsius=62),
        _sample(health_score=90, predictive_risk_score=24, temperature_celsius=60),
        _sample(health_score=92, predictive_risk_score=18, temperature_celsius=59),
        _sample(health_score=93, predictive_risk_score=16, temperature_celsius=58),
        _sample(health_score=94, predictive_risk_score=14, temperature_celsius=58),
        _sample(health_score=95, predictive_risk_score=12, temperature_celsius=57),
    ]
    result = verify_remediation(baseline, posts, "inspect_cooling_and_thermal_path")
    assert result["ready"] is True
    assert result["outcome"] == "resolved"
    assert result["confidence"] == 1.0
    assert any("temperature" in item.lower() for item in result["evidence"])


def test_verifier_classifies_partial_improvement():
    baseline = _sample(health_score=65, predictive_risk_score=70, io_pressure_avg10=30)
    posts = [
        _sample(health_score=72, predictive_risk_score=58, io_pressure_avg10=24),
        _sample(health_score=74, predictive_risk_score=55, io_pressure_avg10=23),
        _sample(health_score=75, predictive_risk_score=52, io_pressure_avg10=22),
    ]
    result = verify_remediation(baseline, posts, "inspect_storage_latency_and_io_contention")
    assert result["ready"] is True
    assert result["outcome"] in {"improved", "resolved"}


def test_verifier_detects_regression():
    baseline = _sample(health_score=78, predictive_risk_score=45, filesystem_used_percent=85)
    posts = [
        _sample(health_score=60, predictive_risk_score=75, filesystem_used_percent=96),
        _sample(health_score=58, predictive_risk_score=80, filesystem_used_percent=97),
        _sample(health_score=55, predictive_risk_score=85, filesystem_used_percent=98),
    ]
    result = verify_remediation(baseline, posts, "free_or_expand_filesystem_capacity")
    assert result["ready"] is True
    assert result["outcome"] == "worsened"
