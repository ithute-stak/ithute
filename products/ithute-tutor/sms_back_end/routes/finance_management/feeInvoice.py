from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.finace_management.schemas.feeInvoice import FeeInvoiceCreate, FeeInvoiceResponse, FeeInvoiceUpdate
from database.multi_tenant_school_management.models import StudentEnrollment
from database.session import get_db
from routes.finance_management.service.feeInvoice import (
    create_fee_invoice,
    delete_fee_invoice,
    get_fee_invoice,
    get_fee_invoices,
    update_fee_invoice,
)
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/fee-invoices", tags=["Fee Invoices"])


@router.post("/", response_model=FeeInvoiceResponse)
def create_invoice(
    payload: FeeInvoiceCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "cashier")),
):
    enrolled = (
        db.query(StudentEnrollment)
        .filter(
            StudentEnrollment.student_id == payload.student_id,
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.is_current.is_(True),
        )
        .first()
    )
    if enrolled is None:
        raise HTTPException(status_code=404, detail="Student is not enrolled in this school")
    return create_fee_invoice(db, payload, context.school_id)


@router.get("/", response_model=list[FeeInvoiceResponse])
def get_invoices(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return get_fee_invoices(db, context.school_id)


@router.get("/{invoice_id}", response_model=FeeInvoiceResponse)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    invoice = get_fee_invoice(db, invoice_id, context.school_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found in this school")
    return invoice


@router.put("/{invoice_id}", response_model=FeeInvoiceResponse)
def update_invoice(
    invoice_id: UUID,
    payload: FeeInvoiceUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant")),
):
    invoice = update_fee_invoice(db, invoice_id, payload, context.school_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found in this school")
    return invoice


@router.delete("/{invoice_id}")
def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar")),
):
    invoice = delete_fee_invoice(db, invoice_id, context.school_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found in this school")
    return {"message": "Invoice deleted"}
