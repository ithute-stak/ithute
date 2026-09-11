from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Uuid, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import current_claims
from .db import Base, SessionLocal
from .fleet import _profile, _require_branch, _vehicle
from .models import ServiceKitRule, ServiceRecord, Vehicle


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryItem(Base):
    __tablename__ = "fleet_inventory_items"
    __table_args__ = (
        UniqueConstraint("branch_id", "sku", name="uq_fleet_inventory_branch_sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="service_kit")
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class InventoryMovement(Base):
    __tablename__ = "fleet_inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fleet_inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(80))
    reference_id: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class InventoryItemCreate(BaseModel):
    branch_id: uuid.UUID
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(default="service_kit", min_length=1, max_length=80)
    opening_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    unit: str = Field(default="unit", min_length=1, max_length=40)


class InventoryMovementCreate(BaseModel):
    branch_id: uuid.UUID
    item_id: uuid.UUID
    quantity_delta: Decimal
    movement_type: str = Field(pattern=r"^(receipt|issue|adjustment|service_use)$")
    reference_type: str | None = Field(default=None, max_length=80)
    reference_id: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-inventory"])


def _item_out(row: InventoryItem) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "branch_id": str(row.branch_id),
        "sku": row.sku,
        "name": row.name,
        "category": row.category,
        "quantity_on_hand": float(row.quantity_on_hand),
        "reorder_level": float(row.reorder_level),
        "unit": row.unit,
        "stock_level": "OUT OF STOCK" if row.quantity_on_hand <= 0 else "LOW STOCK" if row.quantity_on_hand <= row.reorder_level else "AVAILABLE",
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def stock_for_kit(db: Session, branch_id: uuid.UUID, kit_name: str | None) -> dict[str, Any]:
    if not kit_name:
        return {"level": "orange", "label": "SERVICE KIT RULE REQUIRED", "detail": "No service-kit rule is configured for this vehicle/service type.", "kit_name": None, "sku": None, "quantity_on_hand": 0}
    item = db.scalar(select(InventoryItem).where(InventoryItem.branch_id == branch_id, func.lower(InventoryItem.name) == kit_name.strip().lower()))
    if item is None:
        return {"level": "red", "label": "STOCK REQUIRED", "detail": f"{kit_name} is required but no matching Fleet inventory item is recorded.", "kit_name": kit_name, "sku": None, "quantity_on_hand": 0}
    quantity = float(item.quantity_on_hand)
    if item.quantity_on_hand <= 0:
        level, label, detail = "red", "STOCK REQUIRED", f"{kit_name} has no stock on hand."
    elif item.quantity_on_hand <= item.reorder_level:
        level, label, detail = "orange", "AVAILABLE · REORDER", f"{kit_name} is available, but stock is at/below the reorder level."
    else:
        level, label, detail = "green", "AVAILABLE", f"{kit_name} is available in Fleet inventory."
    return {"level": level, "label": label, "detail": detail, "kit_name": kit_name, "sku": item.sku, "quantity_on_hand": quantity, "reorder_level": float(item.reorder_level), "unit": item.unit, "source_type": "fleet_inventory_item", "source_id": str(item.id)}


def vehicle_service_kit_stock(db: Session, vehicle: Vehicle, *, service_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    latest_service = db.scalar(select(ServiceRecord).where(ServiceRecord.vehicle_id == vehicle.id).order_by(ServiceRecord.service_date.desc(), ServiceRecord.created_at.desc()).limit(1))
    if latest_service is None:
        return {"level": "green", "label": "KIT CHECK PENDING SERVICE HISTORY", "detail": "A service-kit requirement will be evaluated after service history is recorded.", "kit_name": None, "quantity_on_hand": 0}
    rule = db.scalar(select(ServiceKitRule).where(ServiceKitRule.branch_id == vehicle.branch_id, ServiceKitRule.make.ilike(vehicle.make), ServiceKitRule.model.ilike(vehicle.model), ServiceKitRule.service_type.ilike(latest_service.service_type)))
    kit_name = rule.kit_name if rule else latest_service.service_kit
    result = stock_for_kit(db, vehicle.branch_id, kit_name)
    service_level = str((service_snapshot or {}).get("level") or "")
    if service_level == "green" and result["label"] == "STOCK REQUIRED":
        return {**result, "level": "green", "label": "STOCK CHECK DEFERRED", "detail": f"{kit_name} is not in stock, but the deterministic service threshold is not yet due."}
    return result


@router.get("/inventory")
def list_inventory(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        items = list(db.scalars(select(InventoryItem).where(InventoryItem.branch_id == branch_id).order_by(InventoryItem.category, InventoryItem.name)))
        movements = list(db.scalars(select(InventoryMovement).where(InventoryMovement.branch_id == branch_id).order_by(InventoryMovement.created_at.desc()).limit(100)))
        return {"items": [_item_out(item) for item in items], "recent_movements": [{"id": str(row.id), "item_id": str(row.item_id), "quantity_delta": float(row.quantity_delta), "movement_type": row.movement_type, "reference_type": row.reference_type, "reference_id": row.reference_id, "notes": row.notes, "created_at": row.created_at.isoformat()} for row in movements]}


@router.post("/inventory/items", status_code=201)
def create_inventory_item(payload: InventoryItemCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        row = InventoryItem(branch_id=payload.branch_id, sku=payload.sku.strip().upper(), name=payload.name.strip(), category=payload.category.strip(), quantity_on_hand=payload.opening_quantity, reorder_level=payload.reorder_level, unit=payload.unit.strip())
        db.add(row)
        try:
            db.flush()
            if payload.opening_quantity:
                db.add(InventoryMovement(branch_id=payload.branch_id, item_id=row.id, quantity_delta=payload.opening_quantity, movement_type="receipt", reference_type="opening_balance", notes="Opening Fleet inventory balance.", recorded_by_profile_id=profile.id))
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="inventory SKU already exists in this branch") from None
        db.refresh(row)
        return _item_out(row)


@router.post("/inventory/movements", status_code=201)
def record_inventory_movement(payload: InventoryMovementCreate, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    if payload.quantity_delta == 0:
        raise HTTPException(status_code=422, detail="quantity_delta cannot be zero")
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, payload.branch_id, write=True)
        item = db.get(InventoryItem, payload.item_id)
        if item is None or item.branch_id != payload.branch_id:
            raise HTTPException(status_code=404, detail="inventory item not found in branch")
        new_quantity = item.quantity_on_hand + payload.quantity_delta
        if new_quantity < 0:
            raise HTTPException(status_code=409, detail="movement would make inventory stock negative")
        item.quantity_on_hand = new_quantity
        db.add(InventoryMovement(branch_id=payload.branch_id, item_id=item.id, quantity_delta=payload.quantity_delta, movement_type=payload.movement_type, reference_type=payload.reference_type, reference_id=payload.reference_id, notes=payload.notes, recorded_by_profile_id=profile.id))
        db.commit()
        db.refresh(item)
        return _item_out(item)


@router.get("/inventory/service-kits")
def service_kit_stock(branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        rules = list(db.scalars(select(ServiceKitRule).where(ServiceKitRule.branch_id == branch_id).order_by(ServiceKitRule.make, ServiceKitRule.model, ServiceKitRule.service_type)))
        return [{"rule_id": str(rule.id), "make": rule.make, "model": rule.model, "service_type": rule.service_type, **stock_for_kit(db, branch_id, rule.kit_name)} for rule in rules]


@router.get("/inventory/vehicles/{vehicle_id}/service-kit")
def vehicle_service_kit(vehicle_id: uuid.UUID, branch_id: uuid.UUID = Query(...), claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims)
        _require_branch(db, profile, branch_id)
        vehicle = _vehicle(db, branch_id, vehicle_id)
        return vehicle_service_kit_stock(db, vehicle)
