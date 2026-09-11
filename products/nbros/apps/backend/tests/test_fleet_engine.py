from datetime import date, timedelta

from sqlalchemy import select

from app.fleet_engine import document_status, evaluate_vehicle, match_vehicles
from app.models import (
    DocumentRequirement,
    Driver,
    MechanicalFault,
    Reservation,
    ServiceRecord,
    VehicleDocument,
    VehicleTypeLicenseRule,
)
from conftest import NOW, TODAY


def test_document_status_boundaries():
    doc = VehicleDocument(
        branch_id="00000000-0000-0000-0000-000000000001",
        vehicle_id="00000000-0000-0000-0000-000000000002",
        document_type="Insurance",
        expiry_date=TODAY + timedelta(days=30),
    )
    assert document_status(doc, TODAY, 30, 7)["level"] == "orange"
    doc.expiry_date = TODAY + timedelta(days=7)
    assert document_status(doc, TODAY, 30, 7)["level"] == "red"
    doc.expiry_date = TODAY - timedelta(days=1)
    assert document_status(doc, TODAY, 30, 7)["label"] == "EXPIRED"


def test_healthy_vehicle_is_available_and_green(db, healthy_vehicle):
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["readiness"] == "green"
    assert result["documents"]["overall"]["level"] == "green"
    assert result["service"]["level"] == "green"
    assert result["mechanical"]["level"] == "green"
    assert result["inspection"]["level"] == "green"
    assert result["availability"]["label"] == "AVAILABLE NOW"


def test_missing_required_document_blocks_vehicle(db, branch, healthy_vehicle):
    db.add(DocumentRequirement(branch_id=branch.id, document_type="Insurance", is_required=True))
    db.commit()
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["documents"]["overall"]["level"] == "red"
    assert result["documents"]["items"][0]["label"] == "MISSING"
    assert result["availability"]["level"] == "red"
    assert result["readiness"] == "red"


def test_document_expiry_warning_is_orange_without_blocking_now(db, branch, healthy_vehicle):
    requirement = DocumentRequirement(branch_id=branch.id, document_type="Insurance", is_required=True)
    db.add(requirement)
    db.flush()
    db.add(
        VehicleDocument(
            branch_id=branch.id,
            vehicle_id=healthy_vehicle.id,
            document_type="Insurance",
            document_number="INS-1",
            issue_date=TODAY,
            expiry_date=TODAY + timedelta(days=14),
        )
    )
    db.commit()
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["documents"]["overall"]["level"] == "orange"
    assert result["availability"]["label"] == "AVAILABLE NOW"
    assert result["readiness"] == "orange"


def test_overdue_service_blocks_vehicle(db, healthy_vehicle):
    service = db.scalar(select(ServiceRecord).where(ServiceRecord.vehicle_id == healthy_vehicle.id))
    assert service is not None
    service.next_service_date = TODAY - timedelta(days=1)
    db.commit()
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["service"]["label"] == "SERVICE OVERDUE"
    assert result["availability"]["level"] == "red"
    assert result["readiness"] == "red"


def test_critical_fault_blocks_vehicle(db, branch, healthy_vehicle):
    db.add(
        MechanicalFault(
            branch_id=branch.id,
            vehicle_id=healthy_vehicle.id,
            severity="critical",
            description="Brake system failure",
        )
    )
    db.commit()
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["mechanical"]["label"] == "OUT OF SERVICE"
    assert "Brake system failure" in result["mechanical"]["detail"]
    assert result["readiness"] == "red"


def test_active_reservation_reports_expected_future_availability(db, branch, healthy_vehicle):
    release = NOW + timedelta(hours=4)
    db.add(
        Reservation(
            branch_id=branch.id,
            vehicle_id=healthy_vehicle.id,
            purpose="Site inspection",
            start_at=NOW - timedelta(hours=1),
            end_at=release,
            status="active",
        )
    )
    db.commit()
    result = evaluate_vehicle(db, healthy_vehicle, at=NOW)
    assert result["availability"]["label"] == "EXPECTED LATER"
    assert result["availability"]["level"] == "orange"
    assert result["availability"]["expected_available_at"] == release.isoformat()


def test_match_rejects_unsuitable_driver_licence(db, branch, healthy_vehicle):
    driver = Driver(
        branch_id=branch.id,
        full_name="Test Driver",
        license_number="L-100",
        license_category="C",
        license_expiry=date(2027, 1, 1),
        is_active=True,
    )
    db.add(driver)
    db.add(
        VehicleTypeLicenseRule(
            branch_id=branch.id,
            vehicle_type="Light vehicle",
            license_category="B",
        )
    )
    db.commit()
    result = match_vehicles(
        db,
        branch_id=branch.id,
        vehicle_type="Light vehicle",
        start_at=NOW,
        end_at=NOW + timedelta(hours=2),
        driver_id=driver.id,
    )
    assert result["recommended"] is None
    assert result["driver_error"] == "Driver licence category is not suitable."
