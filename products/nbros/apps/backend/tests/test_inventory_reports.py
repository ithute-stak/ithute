from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.fleet_alerts import FleetAlert, sync_vehicle_alerts
from app.fleet_inventory import InventoryItem, stock_for_kit, vehicle_service_kit_stock
from app.fleet_reports import build_branch_summary, vehicle_history_rows
from app.models import AccidentRecord, FuelRecord, ServiceKitRule, ServiceRecord
from conftest import NOW, TODAY


def test_service_kit_stock_states(db, branch, healthy_vehicle):
    db.add(
        ServiceKitRule(
            branch_id=branch.id,
            make=healthy_vehicle.make,
            model=healthy_vehicle.model,
            service_type="Minor",
            kit_name="Hilux Minor Kit",
        )
    )
    db.commit()

    missing = vehicle_service_kit_stock(db, healthy_vehicle, service_snapshot={"level": "orange"})
    assert missing["label"] == "STOCK REQUIRED"
    assert missing["level"] == "red"

    item = InventoryItem(
        branch_id=branch.id,
        sku="KIT-HILUX-MINOR",
        name="Hilux Minor Kit",
        category="service_kit",
        quantity_on_hand=Decimal("3"),
        reorder_level=Decimal("1"),
        unit="kit",
    )
    db.add(item)
    db.commit()
    available = stock_for_kit(db, branch.id, "Hilux Minor Kit")
    assert available["label"] == "AVAILABLE"
    assert available["level"] == "green"

    item.quantity_on_hand = Decimal("1")
    db.commit()
    low = stock_for_kit(db, branch.id, "Hilux Minor Kit")
    assert low["label"] == "AVAILABLE · REORDER"
    assert low["level"] == "orange"

    item.quantity_on_hand = Decimal("0")
    db.commit()
    empty = stock_for_kit(db, branch.id, "Hilux Minor Kit")
    assert empty["label"] == "STOCK REQUIRED"
    assert empty["level"] == "red"


def test_alert_lifecycle_create_change_and_resolve(db, branch, healthy_vehicle):
    snapshot = {
        "vehicle": {"id": str(healthy_vehicle.id)},
        "documents": {"items": []},
        "service": {"level": "orange", "label": "SERVICE DUE SOON", "detail": "Prepare service.", "source_type": "service_record", "source_id": "svc-1"},
        "mechanical": {"level": "green", "label": "OPERATIONAL", "detail": "ok"},
        "inspection": {"level": "green", "label": "INSPECTION CURRENT", "detail": "ok"},
        "inventory": {"level": "green", "label": "AVAILABLE", "detail": "kit in stock"},
        "availability": {"blockers": []},
    }
    notify = sync_vehicle_alerts(
        db,
        branch_id=branch.id,
        vehicle_id=healthy_vehicle.id,
        snapshot=snapshot,
        now=NOW,
    )
    db.commit()
    assert len(notify) == 1
    alert = db.scalar(select(FleetAlert).where(FleetAlert.vehicle_id == healthy_vehicle.id))
    assert alert is not None
    assert alert.resolved_at is None

    snapshot["service"] = {"level": "green", "label": "SERVICE UP TO DATE", "detail": "ok"}
    notify = sync_vehicle_alerts(
        db,
        branch_id=branch.id,
        vehicle_id=healthy_vehicle.id,
        snapshot=snapshot,
        now=NOW + timedelta(minutes=5),
    )
    db.commit()
    assert notify == []
    db.refresh(alert)
    assert alert.resolved_at is not None


def test_branch_report_and_vehicle_history_are_traceable(db, branch, healthy_vehicle):
    db.add(
        FuelRecord(
            branch_id=branch.id,
            vehicle_id=healthy_vehicle.id,
            recorded_at=NOW,
            mileage=10_100,
            litres=Decimal("40"),
            cost=Decimal("800"),
            station="Test Station",
        )
    )
    db.add(
        AccidentRecord(
            branch_id=branch.id,
            vehicle_id=healthy_vehicle.id,
            occurred_at=NOW,
            location="Maseru",
            description="Minor test incident",
            reference_number="ACC-1",
        )
    )
    existing_service = db.scalar(
        select(ServiceRecord).where(ServiceRecord.vehicle_id == healthy_vehicle.id)
    )
    existing_service.cost = Decimal("500")
    db.commit()

    summary = build_branch_summary(
        db,
        branch.id,
        from_date=TODAY - timedelta(days=1),
        to_date=TODAY + timedelta(days=1),
    )
    assert summary["fleet"]["vehicles"] == 1
    assert summary["costs"]["service_total"] == 500.0
    assert summary["costs"]["fuel_total"] == 800.0
    assert summary["costs"]["fuel_litres"] == 40.0
    assert summary["operations"]["accidents_in_window"] == 1

    history = vehicle_history_rows(db, branch.id, healthy_vehicle.id)
    kinds = {row["kind"] for row in history}
    assert "service" in kinds
    assert "fuel" in kinds
    assert "accident" in kinds
    assert all(row.get("source_id") for row in history)
