from app.api.v1.hardware_intelligence import HardwareEnvelope, _health, _verify_signature, _go_json
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
