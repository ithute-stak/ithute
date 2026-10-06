from datetime import datetime, timedelta, timezone

from app.api.v1.hardware_intelligence import HardwareEnvelope, _go_json, _hardware_incident_summary, _health, _verify_signature, _window_active_at
from app.models import HardwareMaintenanceWindow
import hashlib
import hmac


def _payload() -> dict:
    return {
        "schema_version": 1,
        "sampled_at_unix": 1,
        "uptime_seconds": 1000,
        "load": {"one": 0.2, "five": 0.3, "fifteen": 0.4},
        "memory": {"total_kb": 1000, "available_kb": 700, "swap_total_kb": 0, "swap_free_kb": 0},
        "cpu": {"user": 1, "nice": 0, "system": 1, "idle": 100, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        "thermal": {"zones_seen": 1, "max_celsius": 45.0},
        "pressure": {"cpu_avg10": 0.0, "memory_avg10": 0.0, "io_avg10": 0.0},
        "filesystem": {"root_total_bytes": 1000, "root_available_bytes": 500},
        "block": {"devices": 1, "reads_completed": 1, "sectors_read": 2, "writes_completed": 3, "sectors_written": 4, "io_ms": 5, "weighted_io_ms": 6},
        "capabilities": {"hwmon": True, "thermal": True, "edac": False, "ipmi": False, "bpf_fs": True, "kernel_btf": True, "smartctl": True, "nvme_cli": True},
    }


def _signed_envelope(key: str, payload: dict | None = None) -> HardwareEnvelope:
    body = {
        "envelope_version": 1,
        "algorithm": "HMAC-SHA256",
        "agent_id": "00000000-0000-0000-0000-000000000001",
        "issued_at_unix": 100,
        "nonce": "0123456789abcdef0123456789abcdef",
        "payload": payload or _payload(),
    }
    signature = hmac.new(key.encode(), _go_json(body), hashlib.sha256).hexdigest()
    return HardwareEnvelope(**body, signature=signature)


def test_hardware_envelope_signature_verifies_and_detects_tamper():
    key = "ith_srv_0123456789abcdef0123456789abcdef"
    envelope = _signed_envelope(key)
    assert _verify_signature(envelope, key) is True
    envelope.payload["memory"]["available_kb"] = 701
    assert _verify_signature(envelope, key) is False


def test_hardware_health_is_healthy_for_normal_sample():
    result = _health(_payload())
    assert result["status"] == "healthy"
    assert result["score"] == 100
    assert result["storage_warning_count"] == 0


def test_hardware_health_flags_nvme_failure_and_pressure():
    payload = _payload()
    payload["pressure"]["io_avg10"] = 45.0
    payload["thermal"]["max_celsius"] = 88.0
    payload["storage_devices"] = [{
        "device": "/dev/nvme0n1",
        "protocol": "NVMe",
        "critical_warning": 1,
        "media_errors": 4,
        "percentage_used": 97,
        "temperature_celsius": 80,
    }]
    result = _health(payload)
    assert result["status"] == "critical"
    assert result["score"] < 50
    assert result["storage_warning_count"] >= 1
    assert result["evidence"]



def test_hardware_health_flags_uncorrected_ecc_and_bmc_critical():
    payload = _payload()
    payload["memory_reliability"] = {
        "available": True,
        "corrected_errors": 4,
        "uncorrected_errors": 1,
        "controllers": 2,
    }
    payload["bmc"] = {
        "available": True,
        "sensor_count": 12,
        "critical_count": 1,
        "warning_count": 2,
        "faulty_sensors": ["PSU1 Status"],
    }
    result = _health(payload)
    assert result["status"] == "critical"
    assert result["ecc_uncorrected_errors"] == 1
    assert result["bmc_critical_count"] == 1
    assert any("ECC" in item for item in result["evidence"])
    assert any("BMC" in item for item in result["evidence"])



def test_maintenance_window_active_boundaries():
    now = datetime.now(timezone.utc)
    active = HardwareMaintenanceWindow(
        server_id="00000000-0000-0000-0000-000000000001",
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(minutes=20),
        reason="Planned kernel upgrade",
        suppress_notifications=True,
    )
    assert _window_active_at(active, now) is True

    future = HardwareMaintenanceWindow(
        server_id="00000000-0000-0000-0000-000000000001",
        starts_at=now + timedelta(minutes=5),
        ends_at=now + timedelta(minutes=20),
        reason="Future maintenance",
        suppress_notifications=True,
    )
    assert _window_active_at(future, now) is False

    active.cancelled_at = now
    assert _window_active_at(active, now) is False



def test_hardware_incident_summary_uses_critical_health_over_prediction():
    server = type("Server", (), {"name": "Core VPS 1"})()
    severity, title, summary = _hardware_incident_summary(
        server,
        {"status": "critical", "evidence": ["NVMe media errors increasing"]},
        {"state": "high", "risk_score": 94, "evidence": ["storage drift"]},
    )
    assert severity == "critical"
    assert title == "Critical hardware health on Core VPS 1"
    assert "94/100" in summary
    assert "NVMe media errors increasing" in summary


def test_hardware_incident_reconciliation_contract_exists():
    root = __import__("pathlib").Path(__file__).parents[1]
    api = (root / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    model = (root / "app" / "models" / "hardware_intelligence.py").read_text(encoding="utf-8")

    assert "class HardwareIncident" in model
    assert "def _active_hardware_incident" in api
    assert "def _reconcile_hardware_incident" in api
    assert 'HardwareIncident.status == "open"' in api
    assert 'incident.status = "resolved"' in api
    assert "notification_suppressed=suppressed" in api
    assert 'category="hardware_intelligence"' in api
    assert '@router.get("/incidents")' in api



def test_hardware_notification_and_maintenance_workflow_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "hardware_intelligence.py").read_text(encoding="utf-8")
    worker = (backend / "app" / "services" / "hardware_notifications.py").read_text(encoding="utf-8")
    compose = (repo / "compose.production.yml").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert "class HardwareIncidentDelivery" in models
    assert "class HardwareMaintenanceTask" in models
    assert "_queue_hardware_incident_notifications" in api
    assert "_ensure_hardware_maintenance_task" in api
    assert '@router.get("/maintenance-tasks")' in api
    assert '@router.post("/maintenance-tasks/{task_id}/status")' in api
    assert "dispatch_hardware_incident_deliveries" in worker
    assert "incident.status != \"open\"" in worker
    assert "incident.notification_suppressed" in worker
    assert "ithute-hardware-notification-worker:" in compose
    assert "ithute-notification" in compose
    assert 'searchParams.get("server")' in page
    assert "Incident maintenance task" in page



def test_hardware_operations_observability_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert '@router.get("/operations-summary")' in api
    assert '@router.post("/incidents/{incident_id}/retry-notifications")' in api
    assert 'HardwareIncidentDelivery.status.in_(["failed", "retry"])' in api
    assert 'incident.status != "open"' in api
    assert "incident.notification_suppressed" in api
    assert '"/hardware-intelligence/operations-summary"' in page
    assert "Retry failed notifications" in page
    assert "Delivery failures" in page



def test_hardware_remediation_recommendation_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    runtime = (backend / "app" / "services" / "engine_runtime.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    for signal in (
        '"temperature_celsius": snapshot.temperature_celsius',
        '"memory_pressure_avg10": snapshot.memory_pressure_avg10',
        '"io_pressure_avg10": snapshot.io_pressure_avg10',
        '"filesystem_used_percent": snapshot.filesystem_used_percent',
        '"storage_warning_count": snapshot.storage_warning_count',
    ):
        assert signal in api

    assert '"plan_version": "3"' in runtime
    assert '"recommendations": recommendations' in runtime
    assert "Recommended remediation" in page
    assert 'recommendations?: string[]' in page



def test_ranked_remediation_contract_uses_predictive_context():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    runtime = (backend / "app" / "services" / "engine_runtime.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert '"predictive_risk_score": snapshot.predictive_risk_score' in api
    assert '"predictive_confidence": snapshot.predictive_confidence' in api
    assert '"plan_version": "3"' in runtime
    assert '"ranked_recommendations": ranked_recommendations' in runtime
    assert "priority_score" in page
    assert "confidence_percent" in page
    assert "Ranked remediation" in page



def test_remediation_outcome_learning_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "hardware_intelligence.py").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0084_hardware_remediation_outcomes.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert "remediation_action" in models
    assert "remediation_outcome" in models
    assert "outcome_recorded_at" in migration
    assert "def _remediation_outcome_stats" in api
    assert "def _apply_remediation_learning" in api
    assert "learned_success_rate" in api
    assert "samples" in api
    assert "Complete + record outcome" in page
    assert "Outcome learning:" in page



def test_hardware_command_center_ui_contract_exists():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert "Assembly · C + eBPF · Rust · Go · Python · Java" in page
    assert "From silicon evidence to operator decision" in page
    assert "Live signal matrix" in page
    assert "24-hour hardware behaviour" in page
    assert "Temperature" in page
    assert "Memory pressure" in page
    assert "I/O pressure" in page
    assert "Filesystem used" in page
    assert "Risk movement" in page
    assert "Recovery assurance" in page
    assert "Current measured state" in page
    assert "Ithute does not silently execute destructive hardware remediation" in page



def test_hardware_ai_ensemble_persistence_and_ui_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "hardware_intelligence.py").read_text(encoding="utf-8")
    ai = (backend / "app" / "services" / "hardware_ai.py").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0085_hardware_ai_models.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert "def isolation_forest_signal" in ai
    assert "def change_point_signal" in ai
    assert "def weibull_survival_projection" in ai
    assert "def ensemble_signals" in ai
    assert "The established robust detector is the safety floor" in ai
    assert "unless two independent AI detectors agree strongly" in ai
    assert "Waiting for sufficient confirmed hardware failure labels" in ai
    assert "predictive_models_json" in models
    assert "predictive_models_json=json.dumps" in api
    assert '"predictive_models": json.loads' in api
    assert "predictive_models_json" in migration
    assert "Isolation Forest" in page
    assert "Change point" in page
    assert "72h survival risk" in page
    assert "Supervised boost" in page



def test_remediation_verification_contract_exists():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]
    api = (backend / "app" / "api" / "v1" / "hardware_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "hardware_intelligence.py").read_text(encoding="utf-8")
    verifier = (backend / "app" / "services" / "hardware_remediation_verification.py").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0086_hardware_remediation_verification.py").read_text(encoding="utf-8")
    page = (repo / "apps" / "frontend" / "app" / "system-owner" / "hardware-intelligence" / "page.tsx").read_text(encoding="utf-8")

    assert "remediation_baseline_snapshot_id" in models
    assert "remediation_verified_snapshot_id" in models
    assert "measured_outcome" in models
    assert "verification_confidence" in models
    assert "verification_sample_count" in models
    assert "verification_evidence_json" in models
    assert "def verify_remediation" in verifier
    assert "MIN_VERIFICATION_SAMPLES = 3" in verifier
    assert "TARGET_VERIFICATION_SAMPLES = 6" in verifier
    assert "def _verify_completed_remediation" in api
    assert "remediation_verification = _verify_completed_remediation" in api
    assert "HardwareMaintenanceTask.measured_outcome" in api
    assert "predictive_risk_score" in verifier
    assert "remediation_baseline_snapshot_id" in migration
    assert "Telemetry-verified outcome" in page
    assert "verification_sample_count" in page
    assert "verification_confidence" in page
