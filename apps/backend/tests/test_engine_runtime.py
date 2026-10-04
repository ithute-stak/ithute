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
