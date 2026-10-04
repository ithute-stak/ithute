from types import SimpleNamespace

import pytest

from app.services import engine_router


def test_router_prefers_specialist_engines_by_workload():
    assert engine_router.preferred_engine("mail.mime_scan") == "rust"
    assert engine_router.preferred_engine("mail.sha256") == "rust"
    assert engine_router.preferred_engine("network.concurrent") == "go"
    assert engine_router.preferred_engine("enterprise.xml") == "java"
    assert engine_router.preferred_engine("native.fingerprint") == "cpp"
    assert engine_router.preferred_engine("unknown.operation") == "python"


def test_binary_router_returns_engine_execution(monkeypatch):
    monkeypatch.setitem(
        engine_router._BINARY_OPERATIONS,
        "mail.sha256",
        lambda data: ("abc123", "rust"),
    )

    result = engine_router.execute_binary("mail.sha256", b"payload")

    assert result.operation == "mail.sha256"
    assert result.engine == "rust"
    assert result.value == "abc123"


def test_binary_router_rejects_unknown_operation():
    with pytest.raises(ValueError, match="Unsupported binary engine operation"):
        engine_router.execute_binary("billing.authorize", b"payload")


def test_routing_status_keeps_python_as_fallback():
    status = engine_router.routing_status()

    assert status["mail.mime_scan"] == {"preferred": "rust", "fallback": "python"}
    assert status["network.concurrent"] == {"preferred": "go", "fallback": "python"}
