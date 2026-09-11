from fastapi.testclient import TestClient

from app.fleet_alerts import FleetAlert
from app.main import app


def test_security_headers_and_request_id_are_applied():
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"x-request-id": "nbros-test-request"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "nbros-test-request"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert "app;dur=" in response.headers["server-timing"]


def test_internal_metrics_are_available_without_openapi_exposure():
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "nbros_uptime_seconds" in response.text
    assert "nbros_http_requests_total" in response.text
    assert "/metrics" not in app.openapi()["paths"]


def test_production_api_contract_contains_governance_exports_and_observability():
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/governance/profiles",
        "/api/v1/governance/branch-access",
        "/api/v1/operations/observability",
        "/api/v1/operations/exports/fleet.csv",
        "/api/v1/operations/exports/tco.csv",
        "/api/v1/operations/exports/audit.csv",
    }
    assert expected <= paths


def test_alert_notification_delivery_fields_are_persisted(db, branch, healthy_vehicle):
    row = FleetAlert(
        branch_id=branch.id,
        vehicle_id=healthy_vehicle.id,
        alert_key="hardening-test",
        severity="orange",
        label="TEST",
        detail="Test alert",
        source_type="vehicle",
        source_id=str(healthy_vehicle.id),
        fingerprint="fingerprint",
        notification_attempts=2,
        last_notification_error="temporary realtime failure",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.notification_attempts == 2
    assert row.last_notification_error == "temporary realtime failure"
