from types import SimpleNamespace

import pytest

from app.services import engine_router


def test_router_prefers_specialist_engines_by_workload():
    assert engine_router.preferred_engine("mail.mime_scan") == "rust"
    assert engine_router.preferred_engine("mail.sha256") == "rust"
    assert engine_router.preferred_engine("crypto.sha256") == "rust"
    assert engine_router.preferred_engine("crypto.hmac_sha256") == "rust"
    assert engine_router.preferred_engine("network.concurrent") == "go"
    assert engine_router.preferred_engine("network.dns") == "go"
    assert engine_router.preferred_engine("network.origin") == "go"
    assert engine_router.preferred_engine("enterprise.xml") == "java"
    assert engine_router.preferred_engine("native.fingerprint") == "cpp"
    assert engine_router.preferred_engine("native.blob_profile") == "cpp"
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


def test_network_router_uses_runtime_result(monkeypatch):
    monkeypatch.setattr(
        engine_router.engine_runtime,
        "network_probe",
        lambda targets, concurrency: (
            {"engine": "go", "checked": len(targets), "results": []},
            "go",
        ),
    )

    result = engine_router.execute_network(
        [{"id": "node:https", "host": "127.0.0.1", "port": 443}],
        concurrency=8,
    )

    assert result.operation == "network.concurrent"
    assert result.engine == "go"
    assert result.value["checked"] == 1


def test_enterprise_xml_router_uses_java_runtime(monkeypatch):
    monkeypatch.setattr(
        engine_router.engine_runtime,
        "enterprise_xml_inspect",
        lambda payload: (
            {
                "engine": "java",
                "root": "report",
                "namespace": "",
                "element_count": 2,
                "attribute_count": 0,
                "text_characters": 4,
                "max_depth": 2,
                "top_elements": [{"name": "report", "count": 1}, {"name": "row", "count": 1}],
            },
            "java",
        ),
    )
    result = engine_router.execute_enterprise_xml(b"<report><row>data</row></report>")
    assert result.operation == "enterprise.xml"
    assert result.engine == "java"
    assert result.value["root"] == "report"


def test_hmac_router_uses_rust_runtime_result(monkeypatch):
    monkeypatch.setattr(
        engine_router.engine_runtime,
        "hmac_sha256",
        lambda key, data: ("deadbeef", "rust"),
    )
    result = engine_router.execute_hmac_sha256(b"key", b"data")
    assert result.engine == "rust"
    assert result.value == "deadbeef"


def test_dns_router_uses_go_runtime_result(monkeypatch):
    monkeypatch.setattr(
        engine_router.engine_runtime,
        "dns_lookup",
        lambda queries, concurrency: (
            {"engine": "go", "checked": len(queries), "results": []},
            "go",
        ),
    )
    result = engine_router.execute_dns(
        [{"id": "a", "name": "example.test", "type": "A"}],
        concurrency=4,
    )
    assert result.operation == "network.dns"
    assert result.engine == "go"
