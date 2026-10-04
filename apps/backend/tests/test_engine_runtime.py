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
