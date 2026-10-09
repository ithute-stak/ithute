"""Offline checks for the read-only developer production smoke tool."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check-developer-portal.py"
spec = importlib.util.spec_from_file_location("developer_portal_smoke", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_network_failures_fail_closed(monkeypatch):
    from urllib.error import URLError
    def fail(*args, **kwargs):
        raise URLError("offline")
    monkeypatch.setattr(module.urllib.request, "urlopen", fail)
    ok, status = module.check("https://ithute.co.ls", "/developer", {200})
    assert not ok
    assert "connection failed" in status

def test_http_200_must_have_html_document(monkeypatch):
    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}
        def read(self, n): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **kw: Response())
    ok, _ = module.check("https://ithute.co.ls", "/developer", {200})
    assert not ok
