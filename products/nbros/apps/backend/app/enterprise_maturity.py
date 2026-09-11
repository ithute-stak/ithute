from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_claims
from .db import SessionLocal
from .enterprise_models import (
    ApprovalRequest,
    BranchFleetBudget,
    GoodsReceipt,
    OperationsSetting,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequisition,
    Supplier,
    TyreAsset,
    WorkshopJobCard,
    WorkshopJobPart,
)
from .enterprise_maturity_models import (
    ApprovalPolicy,
    ApprovalRouting,
    DriverTraining,
    FuelAnalyticsSetting,
    GoodsReceiptLine,
    TyreEvent,
)
from .enterprise_ops import _audit, _tco_rows
from .fleet import _driver, _profile, _require_branch, _vehicle
from .fleet_inventory import InventoryItem, InventoryMovement
from .models import Driver, FuelRecord, MaintenanceWorkOrder, ProfileBranchAccess, Vehicle

router = APIRouter(prefix="/api/v1/operations", tags=["operations-maturity"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def _policy_for(db: Session, branch_id: uuid.UUID, workflow_key: str, amount: Decimal | None) -> ApprovalPolicy | None:
    amount_value = amount or Decimal("0")
    return db.scalar(
        select(ApprovalPolicy)
        .where(
            ApprovalPolicy.branch_id == branch_id,
            ApprovalPolicy.workflow_key == workflow_key,
            ApprovalPolicy.is_active.is_(True),
            ApprovalPolicy.min_amount <= amount_value,
        )
        .order_by(ApprovalPolicy.min_amount.desc(), ApprovalPolicy.priority.asc())
        .limit(1)
    )


def policy_aware_approval(
    db: Session,
    *,
    branch_id: uuid.UUID,
    profile_id: uuid.UUID,
    workflow_key: str,
    entity_type: str,
    entity_id: uuid.UUID,
    amount: Decimal | None,
    reason: str,
) -> ApprovalRequest:
    existing = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.branch_id == branch_id,
            ApprovalRequest.entity_type == entity_type,
            ApprovalRequest.entity_id == entity_id,
            ApprovalRequest.status == "pending",
        )
    )
    if existing:
        route = db.scalar(select(ApprovalRouting).where(ApprovalRouting.approval_request_id == existing.id))
        if route is None:
            policy = _policy_for(db, branch_id, workflow_key, amount)
            db.add(
                ApprovalRouting(
                    approval_request_id=existing.id,
                    policy_id=policy.id if policy else None,
                    required_role=policy.required_role if policy else "manager",
                    stage=1,
                )
            )
        return existing

    row = ApprovalRequest(
        branch_id=branch_id,
        workflow_key=workflow_key,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by_profile_id=profile_id,
        amount=amount,
        reason=reason,
    )
    db.add(row)
    db.flush()
    policy = _policy_for(db, branch_id, workflow_key, amount)
    db.add(
        ApprovalRouting(
            approval_request_id=row.id,
            policy_id=policy.id if policy else None,
            required_role=policy.required_role if policy else "manager",
            stage=1,
        )
    )
    return row


def _require_routed_role(db: Session, profile, branch_id: uuid.UUID, required_role: str) -> None:
    if profile.role in {"admin", "fleet_admin"}:
        return
    membership = db.scalar(
        select(ProfileBranchAccess).where(
            ProfileBranchAccess.profile_id == profile.id,
            ProfileBranchAccess.branch_id == branch_id,
        )
    )
    actual = membership.role if membership else ""
    if required_role in {"viewer", "operator"} and actual:
        return
    if required_role in {"manager", "fleet_manager"} and actual in {"manager", "fleet_manager"}:
        return
    if required_role and actual == required_role:
        return
    raise HTTPException(status_code=403, detail=f"approval requires role: {required_role}")


class ApprovalPolicyCreate(BaseModel):
    branch_id: uuid.UUID
    workflow_key: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    min_amount: Decimal = Field(default=Decimal("0"), ge=0)
    required_role: str = Field(default="manager", min_length=1, max_length=64)
    priority: int = Field(default=100, ge=1, le=10000)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)


class GrnLine(BaseModel):
    purchase_order_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class GrnCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[GrnLine] = Field(min_length=1, max_length=100)


class WorkshopCostUpdate(BaseModel):
    diagnosis: str | None = Field(default=None, max_length=8000)
    work_performed: str | None = Field(default=None, max_length=8000)
    labour_hours: Decimal | None = Field(default=None, ge=0)
    labour_cost: Decimal | None = Field(default=None, ge=0)
    external_cost: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern=r"^(open|diagnosing|waiting_parts|pending_approval|in_progress|completed|cancelled)$")


class TyreFitCreate(BaseModel):
    vehicle_id: uuid.UUID
    wheel_position: str = Field(min_length=1, max_length=80)
    odometer_km: int = Field(ge=0)
    tread_mm: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class TyreRotateCreate(BaseModel):
    wheel_position: str = Field(min_length=1, max_length=80)
    odometer_km: int = Field(ge=0)
    tread_mm: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class TyreInspectionCreate(BaseModel):
    odometer_km: int | None = Field(default=None, ge=0)
    tread_mm: Decimal = Field(ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class DriverTrainingCreate(BaseModel):
    branch_id: uuid.UUID
    driver_id: uuid.UUID
    course_name: str = Field(min_length=1, max_length=180)
    provider: str | None = Field(default=None, max_length=160)
    completed_date: date
    expiry_date: date | None = None
    certificate_reference: str | None = Field(default=None, max_length=180)
    notes: str | None = Field(default=None, max_length=2000)


class FuelSettingUpdate(BaseModel):
    anomaly_l_per_100km: Decimal = Field(ge=1, le=200)
    price_deviation_percent: Decimal = Field(ge=0, le=500)
    minimum_distance_km: int = Field(ge=1, le=5000)


def _fuel_setting(db: Session, branch_id: uuid.UUID) -> FuelAnalyticsSetting:
    row = db.get(FuelAnalyticsSetting, branch_id)
    if row is None:
        row = FuelAnalyticsSetting(branch_id=branch_id)
        db.add(row)
        db.flush()
    return row


def _fuel_analytics(db: Session, branch_id: uuid.UUID) -> dict[str, Any]:
    setting = _fuel_setting(db, branch_id)
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id).order_by(Vehicle.registration_plate)))
    all_records = list(db.scalars(select(FuelRecord).where(FuelRecord.branch_id == branch_id).order_by(FuelRecord.recorded_at, FuelRecord.mileage)))
    prices = [float(row.cost / row.litres) for row in all_records if row.cost is not None and row.litres and row.litres > 0]
    avg_price = sum(prices) / len(prices) if prices else None
    by_vehicle: dict[uuid.UUID, list[FuelRecord]] = {}
    for record in all_records:
        by_vehicle.setdefault(record.vehicle_id, []).append(record)

    vehicle_rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    total_litres = Decimal("0")
    total_cost = Decimal("0")
    for vehicle in vehicles:
        records = by_vehicle.get(vehicle.id, [])
        total_litres += sum((row.litres for row in records), Decimal("0"))
        total_cost += sum((row.cost or Decimal("0") for row in records), Decimal("0"))
        consumptions: list[float] = []
        previous: FuelRecord | None = None
        for record in records:
            reasons: list[str] = []
            consumption = None
            if previous is not None:
                distance = record.mileage - previous.mileage
                if distance >= setting.minimum_distance_km and record.litres > 0:
                    consumption = float(record.litres) / distance * 100
                    consumptions.append(consumption)
                    if consumption > float(setting.anomaly_l_per_100km):
                        reasons.append(f"Consumption {consumption:.1f} L/100km exceeds {float(setting.anomaly_l_per_100km):.1f} threshold")
            unit_price = float(record.cost / record.litres) if record.cost is not None and record.litres and record.litres > 0 else None
            if avg_price and unit_price and unit_price > avg_price * (1 + float(setting.price_deviation_percent) / 100):
                reasons.append(f"Fuel price M {unit_price:.2f}/L is above branch average")
            if reasons:
                anomalies.append({
                    "record_id": str(record.id),
                    "vehicle_id": str(vehicle.id),
                    "registration_plate": vehicle.registration_plate,
                    "recorded_at": record.recorded_at.isoformat(),
                    "mileage": record.mileage,
                    "litres": float(record.litres),
                    "cost": _money(record.cost),
                    "consumption_l_per_100km": round(consumption, 2) if consumption is not None else None,
                    "reasons": reasons,
                })
            previous = record
        vehicle_rows.append({
            "vehicle_id": str(vehicle.id),
            "registration_plate": vehicle.registration_plate,
            "fills": len(records),
            "litres": float(sum((row.litres for row in records), Decimal("0"))),
            "cost": float(sum((row.cost or Decimal("0") for row in records), Decimal("0"))),
            "average_l_per_100km": round(sum(consumptions) / len(consumptions), 2) if consumptions else None,
        })
    return {
        "settings": {
            "anomaly_l_per_100km": float(setting.anomaly_l_per_100km),
            "price_deviation_percent": float(setting.price_deviation_percent),
            "minimum_distance_km": setting.minimum_distance_km,
        },
        "summary": {
            "records": len(all_records),
            "litres": float(total_litres),
            "cost": float(total_cost),
            "average_price_per_litre": round(avg_price, 2) if avg_price is not None else None,
            "anomalies": len(anomalies),
        },
        "vehicles": vehicle_rows,
        "anomalies": anomalies,
    }


@router.get("/governance")
def governance(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        policies = list(db.scalars(select(ApprovalPolicy).where(ApprovalPolicy.branch_id == branch_id).order_by(ApprovalPolicy.workflow_key, ApprovalPolicy.min_amount)))
        approvals = list(db.scalars(select(ApprovalRequest).where(ApprovalRequest.branch_id == branch_id).order_by(ApprovalRequest.requested_at.desc()).limit(200)))
        route_by_request = {row.approval_request_id: row for row in db.scalars(select(ApprovalRouting).join(ApprovalRequest, ApprovalRequest.id == ApprovalRouting.approval_request_id).where(ApprovalRequest.branch_id == branch_id))}
        return {
            "policies": [{"id": str(row.id), "workflow_key": row.workflow_key, "display_name": row.display_name, "min_amount": _money(row.min_amount), "required_role": row.required_role, "priority": row.priority, "is_active": row.is_active} for row in policies],
            "approvals": [{"id": str(row.id), "workflow_key": row.workflow_key, "entity_type": row.entity_type, "entity_id": str(row.entity_id), "status": row.status, "amount": _money(row.amount), "reason": row.reason, "requested_at": row.requested_at.isoformat(), "required_role": (route_by_request.get(row.id).required_role if route_by_request.get(row.id) else "manager")} for row in approvals],
        }


@router.post("/approval-policies", status_code=201)
def create_approval_policy(payload: ApprovalPolicyCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = ApprovalPolicy(**payload.model_dump())
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="approval policy tier already exists") from None
        _audit(db, profile.id, payload.branch_id, "approval.policy.created", "approval_policy", row.id, {"workflow_key": row.workflow_key, "required_role": row.required_role, "min_amount": str(row.min_amount)})
        db.commit()
        return {"id": str(row.id), "workflow_key": row.workflow_key, "required_role": row.required_role}


@router.post("/approval-policies/{policy_id}/toggle")
def toggle_approval_policy(policy_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        row = db.get(ApprovalPolicy, policy_id)
        if row is None or row.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="approval policy not found in branch")
        row.is_active = not row.is_active
        _audit(db, profile.id, branch_id, "approval.policy.toggled", "approval_policy", row.id, {"is_active": row.is_active})
        db.commit()
        return {"id": str(row.id), "is_active": row.is_active}


@router.post("/approvals/{approval_id}/decide-routed")
def decide_routed_approval(approval_id: uuid.UUID, payload: ApprovalDecision, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, str]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        row = db.get(ApprovalRequest, approval_id)
        if row is None or row.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="approval not found in branch")
        if row.status != "pending":
            raise HTTPException(status_code=409, detail="approval has already been decided")
        route = db.scalar(select(ApprovalRouting).where(ApprovalRouting.approval_request_id == row.id))
        _require_routed_role(db, profile, branch_id, route.required_role if route else "manager")
        approved = payload.decision == "approve"
        row.status = "approved" if approved else "rejected"
        row.decided_by_profile_id = profile.id
        row.decision_note = payload.note
        row.decided_at = _utcnow()
        if row.entity_type == "workshop_job":
            job = db.get(WorkshopJobCard, row.entity_id)
            if job and job.branch_id == branch_id:
                job.status = "in_progress" if approved else "cancelled"
                maintenance = db.get(MaintenanceWorkOrder, job.maintenance_work_order_id) if job.maintenance_work_order_id else None
                if maintenance:
                    maintenance.status = "in_progress" if approved else "closed"
                    maintenance.closed_at = None if approved else _utcnow()
        elif row.entity_type == "purchase_requisition":
            requisition = db.get(PurchaseRequisition, row.entity_id)
            if requisition and requisition.branch_id == branch_id:
                requisition.status = row.status
        _audit(db, profile.id, branch_id, f"approval.routed.{row.status}", row.entity_type, row.entity_id, {"note": payload.note, "required_role": route.required_role if route else "manager"})
        db.commit()
        return {"status": row.status}


@router.get("/procurement/purchase-orders/{purchase_order_id}/detail")
def purchase_order_detail(purchase_order_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        order = db.get(PurchaseOrder, purchase_order_id)
        if order is None or order.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="purchase order not found in branch")
        supplier = db.get(Supplier, order.supplier_id)
        lines = list(db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id).order_by(PurchaseOrderItem.description)))
        receipts = list(db.scalars(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == order.id).order_by(GoodsReceipt.received_at.desc())))
        receipt_ids = [row.id for row in receipts]
        grn_lines = list(db.scalars(select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id.in_(receipt_ids)))) if receipt_ids else []
        by_receipt: dict[uuid.UUID, list[GoodsReceiptLine]] = {}
        for line in grn_lines:
            by_receipt.setdefault(line.goods_receipt_id, []).append(line)
        return {
            "id": str(order.id), "reference": order.reference, "status": order.status, "supplier": supplier.name if supplier else None,
            "total_amount": _money(order.total_amount), "issued_at": order.issued_at.isoformat(), "expected_at": order.expected_at.isoformat() if order.expected_at else None,
            "lines": [{"id": str(line.id), "inventory_item_id": str(line.inventory_item_id) if line.inventory_item_id else None, "description": line.description, "quantity": float(line.quantity), "unit_cost": _money(line.unit_cost), "received_quantity": float(line.received_quantity), "outstanding_quantity": float(line.quantity - line.received_quantity)} for line in lines],
            "grns": [{"id": str(receipt.id), "reference": receipt.reference, "received_at": receipt.received_at.isoformat(), "notes": receipt.notes, "lines": [{"purchase_order_item_id": str(line.purchase_order_item_id), "quantity": float(line.quantity), "unit_cost": _money(line.unit_cost)} for line in by_receipt.get(receipt.id, [])]} for receipt in receipts],
        }


@router.get("/procurement/grns")
def list_grns(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        receipts = list(db.scalars(select(GoodsReceipt).where(GoodsReceipt.branch_id == branch_id).order_by(GoodsReceipt.received_at.desc()).limit(200)))
        return [{"id": str(row.id), "purchase_order_id": str(row.purchase_order_id), "reference": row.reference, "notes": row.notes, "received_at": row.received_at.isoformat()} for row in receipts]


@router.post("/procurement/purchase-orders/{purchase_order_id}/grn", status_code=201)
def post_grn(purchase_order_id: uuid.UUID, payload: GrnCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        order = db.get(PurchaseOrder, purchase_order_id)
        if order is None or order.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="purchase order not found in branch")
        if order.status == "received":
            raise HTTPException(status_code=409, detail="purchase order is already fully received")
        receipt = GoodsReceipt(branch_id=branch_id, purchase_order_id=order.id, reference=payload.reference.strip(), received_by_profile_id=profile.id, notes=payload.notes)
        db.add(receipt)
        db.flush()
        for incoming in payload.lines:
            line = db.get(PurchaseOrderItem, incoming.purchase_order_item_id)
            if line is None or line.purchase_order_id != order.id:
                raise HTTPException(status_code=404, detail="purchase order line not found")
            outstanding = line.quantity - line.received_quantity
            if incoming.quantity > outstanding:
                raise HTTPException(status_code=409, detail=f"receipt exceeds outstanding quantity for {line.description}")
            line.received_quantity += incoming.quantity
            db.add(GoodsReceiptLine(goods_receipt_id=receipt.id, purchase_order_item_id=line.id, inventory_item_id=line.inventory_item_id, quantity=incoming.quantity, unit_cost=line.unit_cost))
            if line.inventory_item_id:
                item = db.get(InventoryItem, line.inventory_item_id)
                if item and item.branch_id == branch_id:
                    item.quantity_on_hand += incoming.quantity
                    db.add(InventoryMovement(branch_id=branch_id, item_id=item.id, quantity_delta=incoming.quantity, movement_type="receipt", reference_type="goods_receipt", reference_id=str(receipt.id), notes=f"GRN {receipt.reference} against {order.reference}.", recorded_by_profile_id=profile.id))
        all_lines = list(db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id)))
        order.status = "received" if all(line.received_quantity >= line.quantity for line in all_lines) else "part_received"
        if order.status == "received":
            requisition = db.get(PurchaseRequisition, order.requisition_id)
            if requisition:
                requisition.status = "received"
        _audit(db, profile.id, branch_id, "procurement.grn.posted", "goods_receipt", receipt.id, {"purchase_order": order.reference, "grn": receipt.reference, "status": order.status})
        db.commit()
        return {"grn_id": str(receipt.id), "reference": receipt.reference, "purchase_order_status": order.status}


@router.get("/workshop/costing")
def workshop_costing(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        jobs = list(db.scalars(select(WorkshopJobCard).where(WorkshopJobCard.branch_id == branch_id).order_by(WorkshopJobCard.opened_at.desc()).limit(200)))
        result = []
        for job in jobs:
            parts = list(db.scalars(select(WorkshopJobPart).where(WorkshopJobPart.job_id == job.id)))
            part_rows = []
            parts_total = Decimal("0")
            for part in parts:
                item = db.get(InventoryItem, part.inventory_item_id)
                amount = part.quantity * (part.unit_cost or Decimal("0"))
                parts_total += amount
                part_rows.append({"id": str(part.id), "inventory_item_id": str(part.inventory_item_id), "sku": item.sku if item else None, "name": item.name if item else None, "quantity": float(part.quantity), "unit_cost": _money(part.unit_cost), "amount": float(amount)})
            labour = job.labour_cost or Decimal("0")
            external = job.external_cost or Decimal("0")
            result.append({"job_id": str(job.id), "vehicle_id": str(job.vehicle_id), "status": job.status, "labour_hours": _money(job.labour_hours), "labour_cost": float(labour), "external_cost": float(external), "parts_cost": float(parts_total), "total_cost": float(labour + external + parts_total), "parts": part_rows})
        return result


@router.patch("/workshop/jobs/{job_id}/costing")
def update_workshop_costing(job_id: uuid.UUID, payload: WorkshopCostUpdate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        row = db.get(WorkshopJobCard, job_id)
        if row is None or row.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="workshop job not found in branch")
        values = payload.model_dump(exclude_unset=True)
        for key, value in values.items():
            setattr(row, key, value)
        _audit(db, profile.id, branch_id, "workshop.costing.updated", "workshop_job", row.id, values)
        db.commit()
        return {"id": str(row.id), "status": row.status, "labour_hours": _money(row.labour_hours), "labour_cost": _money(row.labour_cost), "external_cost": _money(row.external_cost)}


@router.get("/tyres/history")
def tyre_history(branch_id: uuid.UUID = Query(...), tyre_id: uuid.UUID | None = Query(default=None), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        query = select(TyreEvent).where(TyreEvent.branch_id == branch_id)
        if tyre_id:
            query = query.where(TyreEvent.tyre_id == tyre_id)
        rows = list(db.scalars(query.order_by(TyreEvent.occurred_at.desc()).limit(500)))
        return [{"id": str(row.id), "tyre_id": str(row.tyre_id), "vehicle_id": str(row.vehicle_id) if row.vehicle_id else None, "event_type": row.event_type, "wheel_position": row.wheel_position, "odometer_km": row.odometer_km, "tread_mm": float(row.tread_mm) if row.tread_mm is not None else None, "notes": row.notes, "occurred_at": row.occurred_at.isoformat()} for row in rows]


def _tyre(db: Session, tyre_id: uuid.UUID, branch_id: uuid.UUID) -> TyreAsset:
    row = db.get(TyreAsset, tyre_id)
    if row is None or row.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="tyre not found in branch")
    return row


@router.post("/tyres/{tyre_id}/lifecycle/fit")
def fit_tyre_lifecycle(tyre_id: uuid.UUID, payload: TyreFitCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        tyre = _tyre(db, tyre_id, branch_id)
        vehicle = _vehicle(db, branch_id, payload.vehicle_id)
        if tyre.status == "fitted" and tyre.vehicle_id:
            raise HTTPException(status_code=409, detail="tyre is already fitted")
        tyre.vehicle_id = vehicle.id
        tyre.wheel_position = payload.wheel_position
        tyre.fitted_at_mileage = payload.odometer_km
        tyre.current_tread_mm = payload.tread_mm
        tyre.fitted_at = _utcnow()
        tyre.removed_at = None
        tyre.status = "fitted"
        event = TyreEvent(branch_id=branch_id, tyre_id=tyre.id, vehicle_id=vehicle.id, event_type="fitted", wheel_position=payload.wheel_position, odometer_km=payload.odometer_km, tread_mm=payload.tread_mm, notes=payload.notes, recorded_by_profile_id=profile.id)
        db.add(event)
        _audit(db, profile.id, branch_id, "tyre.lifecycle.fitted", "tyre", tyre.id, {"vehicle_id": str(vehicle.id), "wheel_position": payload.wheel_position})
        db.commit()
        return {"status": tyre.status, "vehicle_id": str(vehicle.id), "wheel_position": tyre.wheel_position}


@router.post("/tyres/{tyre_id}/lifecycle/rotate")
def rotate_tyre_lifecycle(tyre_id: uuid.UUID, payload: TyreRotateCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        tyre = _tyre(db, tyre_id, branch_id)
        if tyre.status != "fitted" or not tyre.vehicle_id:
            raise HTTPException(status_code=409, detail="tyre must be fitted before rotation")
        previous = tyre.wheel_position
        tyre.wheel_position = payload.wheel_position
        tyre.current_tread_mm = payload.tread_mm if payload.tread_mm is not None else tyre.current_tread_mm
        db.add(TyreEvent(branch_id=branch_id, tyre_id=tyre.id, vehicle_id=tyre.vehicle_id, event_type="rotated", wheel_position=payload.wheel_position, odometer_km=payload.odometer_km, tread_mm=payload.tread_mm, notes=payload.notes or f"Rotated from {previous or 'unknown'}.", recorded_by_profile_id=profile.id))
        _audit(db, profile.id, branch_id, "tyre.lifecycle.rotated", "tyre", tyre.id, {"from": previous, "to": payload.wheel_position})
        db.commit()
        return {"status": tyre.status, "wheel_position": tyre.wheel_position}


@router.post("/tyres/{tyre_id}/lifecycle/inspect")
def inspect_tyre_lifecycle(tyre_id: uuid.UUID, payload: TyreInspectionCreate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        tyre = _tyre(db, tyre_id, branch_id)
        tyre.current_tread_mm = payload.tread_mm
        db.add(TyreEvent(branch_id=branch_id, tyre_id=tyre.id, vehicle_id=tyre.vehicle_id, event_type="inspected", wheel_position=tyre.wheel_position, odometer_km=payload.odometer_km, tread_mm=payload.tread_mm, notes=payload.notes, recorded_by_profile_id=profile.id))
        db.commit()
        return {"status": tyre.status, "tread_mm": float(tyre.current_tread_mm)}


@router.post("/tyres/{tyre_id}/lifecycle/remove")
def remove_tyre_lifecycle(tyre_id: uuid.UUID, branch_id: uuid.UUID = Query(...), odometer_km: int | None = Query(default=None, ge=0), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        tyre = _tyre(db, tyre_id, branch_id)
        vehicle_id = tyre.vehicle_id
        position = tyre.wheel_position
        db.add(TyreEvent(branch_id=branch_id, tyre_id=tyre.id, vehicle_id=vehicle_id, event_type="removed", wheel_position=position, odometer_km=odometer_km, tread_mm=tyre.current_tread_mm, recorded_by_profile_id=profile.id))
        tyre.vehicle_id = None
        tyre.wheel_position = None
        tyre.removed_at = _utcnow()
        tyre.status = "in_stock"
        _audit(db, profile.id, branch_id, "tyre.lifecycle.removed", "tyre", tyre.id, {"vehicle_id": str(vehicle_id) if vehicle_id else None, "position": position})
        db.commit()
        return {"status": tyre.status}


@router.get("/drivers/compliance")
def driver_compliance(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        from .enterprise_models import DriverCredential
        drivers = list(db.scalars(select(Driver).where(Driver.branch_id == branch_id).order_by(Driver.full_name)))
        today = date.today()
        result = []
        for driver in drivers:
            credentials = list(db.scalars(select(DriverCredential).where(DriverCredential.driver_id == driver.id).order_by(DriverCredential.expiry_date)))
            training = list(db.scalars(select(DriverTraining).where(DriverTraining.driver_id == driver.id).order_by(DriverTraining.completed_date.desc())))
            credential_rows = []
            for row in credentials:
                days = (row.expiry_date - today).days if row.expiry_date else None
                status = "expired" if days is not None and days < 0 else "expiring" if days is not None and days <= 30 else "valid"
                credential_rows.append({"id": str(row.id), "credential_type": row.credential_type, "reference": row.reference, "issue_date": row.issue_date.isoformat() if row.issue_date else None, "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None, "status": status})
            training_rows = []
            for row in training:
                days = (row.expiry_date - today).days if row.expiry_date else None
                status = "expired" if days is not None and days < 0 else "expiring" if days is not None and days <= 30 else "current"
                training_rows.append({"id": str(row.id), "course_name": row.course_name, "provider": row.provider, "completed_date": row.completed_date.isoformat(), "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None, "certificate_reference": row.certificate_reference, "status": status})
            licence_days = (driver.license_expiry - today).days
            compliance = "red" if licence_days < 0 or any(x["status"] == "expired" for x in credential_rows + training_rows) else "orange" if licence_days <= 30 or any(x["status"] == "expiring" for x in credential_rows + training_rows) else "green"
            result.append({"driver_id": str(driver.id), "full_name": driver.full_name, "employee_number": driver.employee_number, "license_number": driver.license_number, "license_category": driver.license_category, "license_expiry": driver.license_expiry.isoformat(), "compliance": compliance, "credentials": credential_rows, "training": training_rows})
        return result


@router.post("/drivers/training", status_code=201)
def create_driver_training(payload: DriverTrainingCreate, claims: dict = Depends(current_claims)) -> dict[str, str]:
    if payload.expiry_date and payload.expiry_date < payload.completed_date:
        raise HTTPException(status_code=422, detail="training expiry cannot precede completion")
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        _driver(db, payload.branch_id, payload.driver_id)
        row = DriverTraining(**payload.model_dump())
        db.add(row)
        db.flush()
        _audit(db, profile.id, payload.branch_id, "driver.training.created", "driver_training", row.id, {"driver_id": str(row.driver_id), "course": row.course_name})
        db.commit()
        return {"id": str(row.id)}


@router.get("/fuel/analytics")
def fuel_analytics(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        result = _fuel_analytics(db, branch_id)
        db.commit()
        return result


@router.put("/fuel/settings")
def update_fuel_settings(payload: FuelSettingUpdate, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id, write=True)
        row = _fuel_setting(db, branch_id)
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        _audit(db, profile.id, branch_id, "fuel.analytics.settings.updated", "fuel_analytics_setting", branch_id, payload.model_dump())
        db.commit()
        return {"anomaly_l_per_100km": float(row.anomaly_l_per_100km), "price_deviation_percent": float(row.price_deviation_percent), "minimum_distance_km": row.minimum_distance_km}


@router.get("/finance/management-report")
def finance_management_report(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        tco_rows = _tco_rows(db, branch_id)
        year = _utcnow().year
        budgets = list(db.scalars(select(BranchFleetBudget).where(BranchFleetBudget.branch_id == branch_id, BranchFleetBudget.year == year)))
        budget_total = sum((row.budget_amount for row in budgets), Decimal("0"))
        known_cost = Decimal(str(sum(row["known_cost"] for row in tco_rows)))
        open_commitments = db.scalar(select(func.coalesce(func.sum(PurchaseOrder.total_amount), 0)).where(PurchaseOrder.branch_id == branch_id, PurchaseOrder.status.in_(["issued", "part_received"]))) or 0
        fuel = _fuel_analytics(db, branch_id)
        category_totals = {
            "fuel": round(sum(row["fuel"] for row in tco_rows), 2),
            "service": round(sum(row["service"] for row in tco_rows), 2),
            "workshop_labour": round(sum(row["workshop_labour"] for row in tco_rows), 2),
            "external_repairs": round(sum(row["external_repairs"] for row in tco_rows), 2),
            "tyres": round(sum(row["tyres"] for row in tco_rows), 2),
            "insurance_excess": round(sum(row["insurance_excess"] for row in tco_rows), 2),
        }
        ranked = sorted(tco_rows, key=lambda row: row["known_cost"], reverse=True)
        return {
            "year": year,
            "budget": {"annual_budget": float(budget_total), "known_cost": float(known_cost), "open_procurement_commitments": float(open_commitments), "forecast_committed_total": float(known_cost + Decimal(str(open_commitments))), "variance_to_budget": float(budget_total - known_cost - Decimal(str(open_commitments)))},
            "categories": category_totals,
            "fuel": fuel,
            "vehicles": ranked,
            "top_cost_vehicles": ranked[:10],
            "cost_per_vehicle": round(float(known_cost) / len(tco_rows), 2) if tco_rows else 0,
        }
