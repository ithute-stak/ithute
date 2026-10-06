from app.services import engine_runtime


def test_python_fallback_matches_engine_contract(monkeypatch):
    monkeypatch.setattr(engine_runtime, "_load_rust", lambda: None)
    monkeypatch.setattr(engine_runtime, "_load_cpp", lambda: None)

    raw = "Subject: hello\n\n📧".encode("utf-8")
    result = engine_runtime.sample_native_result(raw)

    assert result["stats_engine"] == "python-fallback"
    assert result["fingerprint_engine"] == "python-fallback"
    assert result["sha256_engine"] == "python-fallback"
    assert result["stats"]["bytes"] == len(raw)
    assert result["stats"]["lines"] == 3
    assert result["stats"]["non_ascii"] == len("📧".encode("utf-8"))
    assert result["mime_engine"] == "python-fallback"
    assert result["mime"]["header_bytes"] > 0
    assert result["mime"]["body_bytes"] > 0
    assert result["mime"]["attachment_signals"] == 0
    assert int(result["fingerprint"]) > 0
    assert result["sha256"] == engine_runtime.python_sha256(raw)


def test_engine_status_keeps_python_authoritative(monkeypatch):
    monkeypatch.setattr(engine_runtime, "_load_rust", lambda: None)
    monkeypatch.setattr(engine_runtime, "_load_cpp", lambda: None)
    monkeypatch.setattr(engine_runtime, "go_worker_status", lambda: {"available": False, "engine": "go", "capabilities": []})
    monkeypatch.setattr(engine_runtime, "java_worker_status", lambda: {"available": False, "engine": "java", "capabilities": []})

    status = engine_runtime.engine_status()

    assert status["brain"]["engine"] == "python"
    assert status["brain"]["authoritative"] is True
    assert "authorization" in status["brain"]["responsibilities"]
    assert status["engines"]["rust"]["fallback"] == "python"
    assert status["engines"]["cpp"]["fallback"] == "python"
    assert status["engines"]["java"]["engine"] == "java"



def test_python_mime_scan_detects_attachment_and_structure():
    raw = (
        b"From: sender@example.test\r\n"
        b"Content-Type: multipart/mixed; boundary=x\r\n"
        b"\r\n"
        b"--x\r\n"
        b"Content-Type: text/plain\r\n\r\nhello\r\n"
        b"--x\r\n"
        b"Content-Disposition: attachment; filename=\"invoice.pdf\"\r\n"
        b"Content-Type: application/pdf\r\n\r\nPDF\r\n"
        b"--x--\r\n"
    )
    scan = engine_runtime.python_mime_scan(raw)

    assert scan.bytes == len(raw)
    assert scan.header_bytes > 0
    assert scan.body_bytes == len(raw) - scan.header_bytes
    assert scan.boundary_markers >= 3
    assert scan.attachment_signals == 1
    assert scan.nul_bytes == 0


def test_python_mime_scan_plain_message_allows_attachment_walk_skip():
    raw = b"From: sender@example.test\r\nSubject: Hello\r\n\r\nPlain body"
    scan = engine_runtime.python_mime_scan(raw)

    assert scan.attachment_signals == 0
    assert scan.boundary_markers == 0


def test_python_sha256_matches_known_vector():
    assert engine_runtime.python_sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_go_network_probe_falls_back_to_python(monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise engine_runtime.httpx.ConnectError("offline")

    monkeypatch.setattr(engine_runtime.httpx, "Client", BrokenClient)
    monkeypatch.setattr(
        engine_runtime,
        "python_network_probe",
        lambda targets, concurrency=16: {
            "engine": "python-fallback",
            "checked": len(targets),
            "results": [
                {
                    "id": targets[0]["id"],
                    "host": targets[0]["host"],
                    "port": targets[0]["port"],
                    "reachable": True,
                    "latency_ms": 0.1,
                }
            ],
        },
    )

    body, engine = engine_runtime.network_probe(
        [{"id": "local:https", "host": "127.0.0.1", "port": 443}],
        concurrency=4,
    )

    assert engine == "python-fallback"
    assert body["engine"] == "python-fallback"
    assert body["checked"] == 1
    assert body["results"][0]["reachable"] is True


def test_python_enterprise_xml_inspection_summary():
    xml = b'<invoice xmlns="urn:ithute:test" id="A1"><line qty="2">Service</line><line qty="1">Hosting</line></invoice>'
    result = engine_runtime.python_enterprise_xml_inspect(xml)

    assert result["engine"] == "python-fallback"
    assert result["root"] == "invoice"
    assert result["namespace"] == "urn:ithute:test"
    assert result["element_count"] == 3
    assert result["attribute_count"] == 3
    assert result["max_depth"] == 2
    assert result["top_elements"][0] == {"name": "line", "count": 2}


def test_enterprise_xml_rejects_doctype_in_python_fallback():
    xml = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>'
    try:
        engine_runtime.python_enterprise_xml_inspect(xml)
    except ValueError as exc:
        assert "DTD/entities" in str(exc)
    else:
        raise AssertionError("DOCTYPE payload should be rejected")


def test_python_blob_profile_matches_reference_values():
    raw = bytes([65, 0, 1, 9, 10, 13, 128, 255])
    profile = engine_runtime.python_blob_profile(raw)

    assert profile.bytes == len(raw)
    assert profile.nul_bytes == 1
    assert profile.control_bytes == 2
    assert profile.high_bytes == 2
    assert profile.fnv1a64 == engine_runtime._python_fnv1a64(raw)


def test_cpp_blob_profile_falls_back_to_python(monkeypatch):
    monkeypatch.setattr(engine_runtime, "_load_cpp", lambda: None)
    raw = b"abc\x00\x01\xff"

    profile, engine = engine_runtime.blob_profile(raw)

    assert engine == "python-fallback"
    assert profile == engine_runtime.python_blob_profile(raw)


def test_python_hmac_sha256_matches_known_vector():
    assert engine_runtime.python_hmac_sha256(
        b"key",
        b"The quick brown fox jumps over the lazy dog",
    ) == "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"


def test_go_dns_lookup_falls_back_to_python(monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise engine_runtime.httpx.ConnectError("offline")

    monkeypatch.setattr(engine_runtime.httpx, "Client", BrokenClient)
    monkeypatch.setattr(
        engine_runtime,
        "python_dns_lookup",
        lambda queries, concurrency=16: {
            "engine": "python-fallback",
            "checked": len(queries),
            "results": [{"id": "a", "name": "example.test", "type": "A", "values": ["203.0.113.1"]}],
        },
    )
    body, engine = engine_runtime.dns_lookup(
        [{"id": "a", "name": "example.test", "type": "A"}],
        concurrency=4,
    )
    assert engine == "python-fallback"
    assert body["checked"] == 1


def test_go_origin_probe_returns_fallback_marker(monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise engine_runtime.httpx.ConnectError("offline")

    monkeypatch.setattr(engine_runtime.httpx, "Client", BrokenClient)
    body, engine = engine_runtime.go_origin_probe({
        "scheme": "https",
        "hostname": "example.test",
        "target_ip": "1.1.1.1",
        "port": 443,
        "path": "/",
        "expected_status": 200,
        "timeout_ms": 1000,
    })
    assert body is None
    assert engine == "python-fallback"



def test_python_hardware_workflow_plan_critical():
    plan = engine_runtime.python_hardware_workflow_plan({
        "severity": "critical",
        "health_status": "critical",
        "predictive_state": "high",
        "notification_suppressed": False,
    })
    assert plan["engine"] == "python-fallback"
    assert plan["escalation"] == "immediate"
    assert "block_new_placement" in plan["actions"]
    assert "drain_after_safety_window" in plan["actions"]
    assert "notify_platform_owner" in plan["actions"]


def test_python_hardware_workflow_plan_respects_maintenance_suppression():
    plan = engine_runtime.python_hardware_workflow_plan({
        "severity": "high",
        "health_status": "warning",
        "predictive_state": "high",
        "notification_suppressed": True,
    })
    assert plan["escalation"] == "maintenance_suppressed"
    assert plan["actions"] == ["record_incident", "suppress_notifications"]


def test_hardware_workflow_plan_falls_back_when_java_is_offline(monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise engine_runtime.httpx.ConnectError("offline")

    monkeypatch.setattr(engine_runtime.httpx, "Client", BrokenClient)
    body, engine = engine_runtime.hardware_workflow_plan({
        "severity": "high",
        "health_status": "warning",
        "predictive_state": "high",
        "notification_suppressed": False,
    })
    assert engine == "python-fallback"
    assert body["escalation"] == "urgent"
    assert "prepare_drain" in body["actions"]
