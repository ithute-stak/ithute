from starlette.requests import Request

from app.models import TrustedDevice
from app.services.identity_security import (
    assess_login_risk,
    generate_recovery_codes,
    normalize_recovery_code,
    issue_adaptive_challenge,
    verify_adaptive_challenge,
    recent_mail_threat_context,
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



class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self.ops = []

    def setex(self, key, ttl, value):
        self.ops.append(("setex", key, ttl, value))
        return self

    def delete(self, key):
        self.ops.append(("delete", key))
        return self

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "setex":
                _, key, ttl, value = op
                self.client.values[key] = value
                self.client.ttls[key] = ttl
                out.append(True)
            elif op[0] == "delete":
                _, key = op
                out.append(1 if self.client.values.pop(key, None) is not None else 0)
                self.client.ttls.pop(key, None)
        return out


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return int(existed)

    def ttl(self, key):
        return self.ttls.get(key, -1)

    def pipeline(self):
        return _FakePipeline(self)


def test_adaptive_challenge_is_bound_and_single_use(monkeypatch):
    import uuid
    from app.models import User
    from app.services import identity_security

    fake = _FakeRedis()
    monkeypatch.setattr(identity_security, "_adaptive_redis", lambda: fake)
    user = User(id=uuid.uuid4(), email="user@ithute.co.ls", password_hash="x")

    challenge_id, code, created = issue_adaptive_challenge(
        user=user,
        request=_request(),
        risk={"score": 35, "level": "medium"},
    )

    assert created is True
    assert len(code) == 6
    assert verify_adaptive_challenge(
        user=user,
        request=_request(),
        challenge_id=challenge_id,
        code=code,
    ) is True
    assert verify_adaptive_challenge(
        user=user,
        request=_request(),
        challenge_id=challenge_id,
        code=code,
    ) is False


def test_adaptive_challenge_rejects_different_network(monkeypatch):
    import uuid
    from app.models import User
    from app.services import identity_security

    fake = _FakeRedis()
    monkeypatch.setattr(identity_security, "_adaptive_redis", lambda: fake)
    user = User(id=uuid.uuid4(), email="user@ithute.co.ls", password_hash="x")

    challenge_id, code, _ = issue_adaptive_challenge(
        user=user,
        request=_request(ip="203.0.113.10"),
        risk={"score": 35, "level": "medium"},
    )

    assert verify_adaptive_challenge(
        user=user,
        request=_request(ip="198.51.100.9"),
        challenge_id=challenge_id,
        code=code,
    ) is False


def test_trusted_device_with_network_and_client_change_requires_step_up():
    from datetime import datetime, timezone

    result = assess_login_risk(
        device=_device(trusted_at=datetime.now(timezone.utc)),
        request=_request(ip="198.51.100.30", user_agent="Different Browser"),
        is_new_device=False,
        mfa_verified=False,
    )

    assert result["score"] == 30
    assert result["recommended_action"] == "step_up"



def test_verified_mail_threat_context_amplifies_login_risk():
    from datetime import datetime, timezone

    result = assess_login_risk(
        device=_device(trusted_at=datetime.now(timezone.utc)),
        request=_request(ip="198.51.100.30"),
        is_new_device=False,
        mfa_verified=False,
        contextual_signals=[
            {
                "signal": "recent_verified_phishing_exposure",
                "weight": 12,
                "source": "mail_intelligence",
                "evidence_count": 2,
            }
        ],
    )

    names = {row["signal"] for row in result["signals"]}
    assert "recent_verified_phishing_exposure" in names
    assert result["score"] == 24
    assert result["recommended_action"] == "allow"


def test_mail_threat_context_can_push_suspicious_login_into_step_up():
    from datetime import datetime, timezone

    result = assess_login_risk(
        device=_device(trusted_at=datetime.now(timezone.utc)),
        request=_request(ip="198.51.100.30"),
        is_new_device=False,
        mfa_verified=False,
        contextual_signals=[
            {
                "signal": "recent_verified_bec_exposure",
                "weight": 18,
                "source": "mail_intelligence",
                "evidence_count": 1,
            }
        ],
    )

    assert result["score"] == 30
    assert result["recommended_action"] == "step_up"


def test_contextual_risk_signal_is_bounded():
    from datetime import datetime, timezone

    result = assess_login_risk(
        device=_device(trusted_at=datetime.now(timezone.utc)),
        request=_request(),
        is_new_device=False,
        mfa_verified=False,
        contextual_signals=[
            {
                "signal": "untrusted_context",
                "weight": 999,
                "source": "test",
                "evidence_count": 100,
            }
        ],
    )

    assert result["score"] == 25
    assert result["recommended_action"] == "allow"



def test_recent_mail_threat_context_uses_only_high_confidence_verified_labels():
    import uuid
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from app.models import User

    class _Scalars:
        def all(self):
            return [
                SimpleNamespace(
                    action_taken="phishing",
                    metadata_json={"verified_label": "phishing", "label_confidence": 0.95},
                    created_at=datetime.now(timezone.utc),
                ),
                SimpleNamespace(
                    action_taken="bec",
                    metadata_json={"verified_label": "bec", "label_confidence": 0.72},
                    created_at=datetime.now(timezone.utc),
                ),
            ]

    class _Db:
        def scalars(self, _statement):
            return _Scalars()

    user = User(id=uuid.uuid4(), email="user@ithute.co.ls", password_hash="x")
    context = recent_mail_threat_context(_Db(), user=user)

    assert context["active"] is True
    assert context["signal"] == "recent_verified_phishing_exposure"
    assert context["weight"] == 12
    assert context["verified_threat_count"] == 1


def test_recent_verified_bec_gets_stronger_bounded_weight():
    import uuid
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from app.models import User

    class _Scalars:
        def all(self):
            return [
                SimpleNamespace(
                    action_taken="bec",
                    metadata_json={"verified_label": "bec", "label_confidence": 0.99},
                    created_at=datetime.now(timezone.utc),
                )
            ]

    class _Db:
        def scalars(self, _statement):
            return _Scalars()

    user = User(id=uuid.uuid4(), email="user@ithute.co.ls", password_hash="x")
    context = recent_mail_threat_context(_Db(), user=user)

    assert context["signal"] == "recent_verified_bec_exposure"
    assert context["weight"] == 18
    assert context["highest_confidence"] == 0.99
