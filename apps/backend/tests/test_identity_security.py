from starlette.requests import Request

from app.models import TrustedDevice
from app.services.identity_security import (
    assess_login_risk,
    generate_recovery_codes,
    normalize_recovery_code,
)


def _request(ip: str = "203.0.113.10", user_agent: str = "Test Browser") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "scheme": "https",
            "headers": [(b"user-agent", user_agent.encode())],
            "client": (ip, 443),
            "server": ("ithute.co.ls", 443),
            "query_string": b"",
        }
    )


def _device(**overrides):
    values = {
        "first_ip_address": "203.0.113.10",
        "last_ip_address": "203.0.113.10",
        "first_user_agent": "Test Browser",
        "trusted_at": None,
        "revoked_at": None,
    }
    values.update(overrides)
    return TrustedDevice(**values)


def test_new_device_is_step_up_risk_without_mfa():
    result = assess_login_risk(
        device=_device(),
        request=_request(),
        is_new_device=True,
        mfa_verified=False,
    )

    assert result["score"] == 35
    assert result["level"] == "medium"
    assert result["recommended_action"] == "step_up"
    assert any(row["signal"] == "new_device" for row in result["signals"])


def test_verified_mfa_reduces_new_device_risk():
    result = assess_login_risk(
        device=_device(),
        request=_request(),
        is_new_device=True,
        mfa_verified=True,
    )

    assert result["score"] == 20
    assert result["level"] == "low"
    assert result["recommended_action"] == "allow"


def test_network_and_client_changes_are_explainable():
    result = assess_login_risk(
        device=_device(trusted_at=None),
        request=_request(ip="198.51.100.30", user_agent="Different Browser"),
        is_new_device=False,
        mfa_verified=False,
    )

    names = {row["signal"] for row in result["signals"]}
    assert {"device_not_explicitly_trusted", "network_changed", "client_signature_changed"} <= names
    assert result["score"] == 42
    assert result["recommended_action"] == "step_up"


def test_recovery_codes_are_unique_and_normalize_for_entry():
    codes = generate_recovery_codes()

    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(len(normalize_recovery_code(code)) == 12 for code in codes)
    assert normalize_recovery_code(codes[0].lower()) == normalize_recovery_code(codes[0])
