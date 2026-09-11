import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.enterprise_maturity import _fuel_analytics, policy_aware_approval
from app.enterprise_maturity_models import ApprovalPolicy, ApprovalRouting
from app.main import app
from app.models import FuelRecord
from conftest import NOW


def test_maturity_routes_are_registered():
    paths = set(app.openapi()["paths"])
    required = {
        "/api/v1/operations/governance",
        "/api/v1/operations/approval-policies",
        "/api/v1/operations/procurement/purchase-orders/{purchase_order_id}/detail",
        "/api/v1/operations/procurement/purchase-orders/{purchase_order_id}/grn",
        "/api/v1/operations/workshop/costing",
        "/api/v1/operations/tyres/history",
        "/api/v1/operations/drivers/compliance",
        "/api/v1/operations/drivers/training",
        "/api/v1/operations/fuel/analytics",
        "/api/v1/operations/finance/management-report",
    }
    assert not (required - paths)


def test_policy_routing_selects_highest_matching_tier(db, branch):
    db.add_all([
        ApprovalPolicy(branch_id=branch.id, workflow_key="procurement_high_value", display_name="Manager", min_amount=Decimal("0"), required_role="manager", priority=100),
        ApprovalPolicy(branch_id=branch.id, workflow_key="procurement_high_value", display_name="Executive", min_amount=Decimal("50000"), required_role="admin", priority=10),
    ])
    db.commit()
    request = policy_aware_approval(
        db,
        branch_id=branch.id,
        profile_id=uuid.uuid4(),
        workflow_key="procurement_high_value",
        entity_type="purchase_requisition",
        entity_id=uuid.uuid4(),
        amount=Decimal("75000"),
        reason="High-value vehicle parts order",
    )
    db.flush()
    route = db.scalar(select(ApprovalRouting).where(ApprovalRouting.approval_request_id == request.id))
    assert route is not None
    assert route.required_role == "admin"


def test_fuel_analytics_flags_high_consumption(db, branch, healthy_vehicle):
    db.add_all([
        FuelRecord(branch_id=branch.id, vehicle_id=healthy_vehicle.id, recorded_at=NOW - timedelta(days=2), mileage=9000, litres=Decimal("40"), cost=Decimal("900"), station="A"),
        FuelRecord(branch_id=branch.id, vehicle_id=healthy_vehicle.id, recorded_at=NOW - timedelta(days=1), mileage=9300, litres=Decimal("100"), cost=Decimal("2300"), station="A"),
    ])
    db.commit()
    result = _fuel_analytics(db, branch.id)
    assert result["summary"]["records"] == 2
    assert result["summary"]["anomalies"] >= 1
    assert result["vehicles"][0]["average_l_per_100km"] > 30
