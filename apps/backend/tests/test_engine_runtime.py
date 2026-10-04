from app.services import engine_runtime


def test_python_fallback_matches_engine_contract(monkeypatch):
    monkeypatch.setattr(engine_runtime, "_load_rust", lambda: None)
    monkeypatch.setattr(engine_runtime, "_load_cpp", lambda: None)

    raw = "Subject: hello\n\n📧".encode("utf-8")
    result = engine_runtime.sample_native_result(raw)

    assert result["stats_engine"] == "python-fallback"
    assert result["fingerprint_engine"] == "python-fallback"
    assert result["stats"]["bytes"] == len(raw)
    assert result["stats"]["lines"] == 3
    assert result["stats"]["non_ascii"] == len("📧".encode("utf-8"))
    assert result["mime_engine"] == "python-fallback"
    assert result["mime"]["header_bytes"] > 0
    assert result["mime"]["body_bytes"] > 0
    assert result["mime"]["attachment_signals"] == 0
    assert int(result["fingerprint"]) > 0


def test_engine_status_keeps_python_authoritative(monkeypatch):
    monkeypatch.setattr(engine_runtime, "_load_rust", lambda: None)
    monkeypatch.setattr(engine_runtime, "_load_cpp", lambda: None)
    monkeypatch.setattr(engine_runtime, "go_worker_status", lambda: {"available": False, "engine": "go", "capabilities": []})

    status = engine_runtime.engine_status()

    assert status["brain"]["engine"] == "python"
    assert status["brain"]["authoritative"] is True
    assert "authorization" in status["brain"]["responsibilities"]
    assert status["engines"]["rust"]["fallback"] == "python"
    assert status["engines"]["cpp"]["fallback"] == "python"



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
