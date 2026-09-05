from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.employee_management.model.employee import Employee
from database.multi_tenant_school_management.models.administration import PurchaseOrder, SchoolExpense, StaffLeaveRequest, Supplier
from database.session import get_db
from utils.school_context import SchoolContext, require_school_roles

router = APIRouter(prefix="/administration", tags=["HR, Procurement & Expenses"])
HR_ROLES = ("school_admin", "principal", "vice_principal", "hr", "hr_manager")
FINANCE_ROLES = ("school_admin", "principal", "vice_principal", "bursar", "accountant", "procurement")


class LeaveCreate(BaseModel):
    employee_id: UUID
    leave_type: str = Field(min_length=2, max_length=60)
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveDecision(BaseModel):
    status: Literal["approved", "rejected", "cancelled"]
    review_note: str | None = None


class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_number: str | None = None


class PurchaseOrderCreate(BaseModel):
    supplier_id: UUID | None = None
    order_number: str = Field(min_length=1, max_length=80)
    items: list[dict] = Field(default_factory=list)
    subtotal: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    total_amount: Decimal = Field(default=Decimal("0"), ge=0)


class PurchaseOrderStatus(BaseModel):
    status: Literal["draft", "approved", "ordered", "received", "cancelled"]


class ExpenseCreate(BaseModel):
    supplier_id: UUID | None = None
    purchase_order_id: UUID | None = None
    category: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2)
    amount: Decimal = Field(ge=0)
    expense_date: date
    reference: str | None = None


@router.get("/leave")
def list_leave(db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*HR_ROLES))):
    return db.query(StaffLeaveRequest).filter(StaffLeaveRequest.school_id == context.school_id).order_by(StaffLeaveRequest.created_at.desc()).all()


@router.post("/leave")
def request_leave(payload: LeaveCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*HR_ROLES))):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="leave end date cannot be before start date")
    employee = db.query(Employee).filter(
        Employee.id == payload.employee_id,
        Employee.school_id == context.school_id,
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found in this school workspace")
    request = StaffLeaveRequest(school_id=context.school_id, **payload.model_dump())
    db.add(request); db.commit(); db.refresh(request); return request


@router.put("/leave/{leave_id}/decision")
def decide_leave(leave_id: UUID, payload: LeaveDecision, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*HR_ROLES))):
    request = db.query(StaffLeaveRequest).filter(StaffLeaveRequest.id == leave_id, StaffLeaveRequest.school_id == context.school_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="leave request not found")
    request.status = payload.status
    request.review_note = payload.review_note
    request.reviewed_by = context.user_id
    request.reviewed_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(request); return request


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    return db.query(Supplier).filter(Supplier.school_id == context.school_id, Supplier.status == "active").order_by(Supplier.name.asc()).all()


@router.post("/suppliers")
def add_supplier(payload: SupplierCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    supplier = Supplier(school_id=context.school_id, **payload.model_dump())
    db.add(supplier); db.commit(); db.refresh(supplier); return supplier


@router.get("/purchase-orders")
def purchase_orders(db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    return db.query(PurchaseOrder).filter(PurchaseOrder.school_id == context.school_id).order_by(PurchaseOrder.created_at.desc()).all()


@router.post("/purchase-orders")
def add_purchase_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    if payload.total_amount != payload.subtotal + payload.tax_amount:
        raise HTTPException(status_code=422, detail="purchase order total must equal subtotal plus tax")
    if payload.supplier_id is not None:
        supplier = db.query(Supplier).filter(
            Supplier.id == payload.supplier_id,
            Supplier.school_id == context.school_id,
        ).first()
        if not supplier:
            raise HTTPException(status_code=404, detail="supplier not found in this school workspace")
    order = PurchaseOrder(school_id=context.school_id, **payload.model_dump())
    db.add(order); db.commit(); db.refresh(order); return order


@router.put("/purchase-orders/{order_id}/status")
def update_purchase_order(order_id: UUID, payload: PurchaseOrderStatus, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id, PurchaseOrder.school_id == context.school_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="purchase order not found")
    order.status = payload.status
    if payload.status == "approved":
        order.approved_by = context.user_id
        order.ordered_on = date.today()
    db.commit(); db.refresh(order); return order


@router.get("/expenses")
def expenses(db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    return db.query(SchoolExpense).filter(SchoolExpense.school_id == context.school_id).order_by(SchoolExpense.expense_date.desc()).all()


@router.post("/expenses")
def add_expense(payload: ExpenseCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*FINANCE_ROLES))):
    if payload.supplier_id is not None:
        supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id, Supplier.school_id == context.school_id).first()
        if not supplier:
            raise HTTPException(status_code=404, detail="supplier not found in this school workspace")
    if payload.purchase_order_id is not None:
        order = db.query(PurchaseOrder).filter(PurchaseOrder.id == payload.purchase_order_id, PurchaseOrder.school_id == context.school_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="purchase order not found in this school workspace")
    expense = SchoolExpense(school_id=context.school_id, **payload.model_dump())
    db.add(expense); db.commit(); db.refresh(expense); return expense
