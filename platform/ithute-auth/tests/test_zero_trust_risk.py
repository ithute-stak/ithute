from types import SimpleNamespace

from app.zero_trust import RiskAssessment, assess_login_risk


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class RequestStub:
    def __init__(self, ip="203.0.113.10", user_agent="Example/1.0", device_key=None):
        self.client = SimpleNamespace(host=ip)
        values = {"user-agent": user_agent}
        if device_key:
            values["x-ithute-device-key"] = device_key
        self.headers = Headers(values)


def _user(**overrides):
    values = {
        "last_login_ip": "203.0.113.10",
        "is_platform_admin": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_passkey_on_trusted_device_is_low_risk():
    device = SimpleNamespace(trusted_at=object())
    result = assess_login_risk(
        user=_user(),
        request=RequestStub(),
        device=device,
        auth_method="passkey",
    )
    assert result.score == 0
    assert result.level == "low"
    assert result.reasons == ()


def test_new_ip_and_unknown_device_raise_risk():
    result = assess_login_risk(
        user=_user(),
        request=RequestStub(ip="198.51.100.20"),
        device=None,
        auth_method="password",
    )
    assert result.score == 60
    assert result.level == "medium"
    assert set(result.reasons) == {"new_ip", "unrecognized_device", "password_auth"}


def test_privileged_password_auth_is_high_risk():
    result = assess_login_risk(
        user=_user(is_platform_admin=True),
        request=RequestStub(),
        device=None,
        auth_method="password",
    )
    assert result.score >= 70
    assert result.level == "high"
    assert "privileged_without_passkey" in result.reasons
