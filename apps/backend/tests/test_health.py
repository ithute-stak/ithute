def test_liveness(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert response.headers["x-request-id"]


def test_request_id_is_preserved(client):
    response = client.get("/health/live", headers={"X-Request-ID": "phase2-test-request"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "phase2-test-request"


def test_readiness_checks_postgres_and_redis(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"] == {"postgres": "ok", "redis": "ok"}


def test_legacy_health_alias_remains_compatible(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
