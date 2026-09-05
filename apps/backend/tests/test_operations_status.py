import json

from app.services import operations_status as service


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"status": "success", "data": {"result": [{"value": [1, str(self.value)]}]}}).encode()


def test_query_parses_prometheus_scalar(monkeypatch):
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(1.25))
    assert service._query("up") == 1.25


def test_operations_status(monkeypatch):
    values = iter([1, 1, 1, 1, 4, 1])
    monkeypatch.setattr(service, "_query", lambda expression: next(values))
    result = service.operations_status()
    assert result["status"] == "ok"
    assert result["mail_queue_total"] == 4
    assert all(value == "ok" for value in result["services"].values())


def test_slo_status(monkeypatch):
    values = iter([0.9995, 0.5, 0.25])
    monkeypatch.setattr(service, "_query", lambda expression: next(values))
    result = service.slo_status()
    assert result["window"] == "7d"
    assert result["status"] == "meeting"
    assert result["error_budget_remaining"] == 0.5
