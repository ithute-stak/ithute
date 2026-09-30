from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceInvoice, FinanceInvoiceItem, User
from app.services.finance_audit import finance_activity, log_finance_action
from app.services.finance_invoices import build_default_email_body, build_default_subject
from app.services.finance_ledger import invoice_financial_out
from app.services.finance_reminders import process_due_payment_reminders

router = APIRouter(prefix="/finance", tags=["finance-operations"])


class InvoiceEdit(BaseModel):
    client_name: str = Field(min_length=2, max_length=180)
    recipient_email: EmailStr
    client_address: str = Field(default="", max_length=500)
    description: str = Field(min_length=2, max_length=500)
    details: str = Field(default="", max_length=1200)
    service_period: str = Field(default="", max_length=160)
    quantity: int = Field(default=1, ge=1, le=10000)
    rate_minor: int = Field(ge=0, le=2_000_000_000)
    tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    due_date: date
    email_subject: str | None = Field(default=None, max_length=300)
    email_body: str | None = Field(default=None, max_length=10000)


def _invoice(db: Session, invoice_id: UUID) -> FinanceInvoice:
    row = db.scalar(
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.items),
            selectinload(FinanceInvoice.credit_notes),
        )
        .where(FinanceInvoice.id == invoice_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return row


@router.put("/invoices/{invoice_id}")
def edit_draft_invoice(
    invoice_id: UUID,
    payload: InvoiceEdit,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    invoice = _invoice(db, invoice_id)
    if invoice.sent_at is not None or invoice.status not in {"draft", "failed"}:
        raise HTTPException(status_code=409, detail="Sent or financially active invoices are locked. Use a credit note or replacement invoice instead.")
    if invoice.payments or invoice.credit_notes:
        raise HTTPException(status_code=409, detail="Invoices with payments or credit notes are locked")
    if len(invoice.items) > 1:
        raise HTTPException(status_code=409, detail="Multi-item converted invoices are locked; edit the source quotation/pro-forma before conversion")

    subtotal = payload.quantity * payload.rate_minor
    total = subtotal + payload.tax_minor
    invoice.client_name = payload.client_name.strip()
    invoice.recipient_email = str(payload.recipient_email).lower()
    invoice.client_address = payload.client_address.strip()
    invoice.description = payload.description.strip()
    invoice.details = payload.details.strip()
    invoice.service_period = payload.service_period.strip()
    invoice.quantity = payload.quantity
    invoice.rate_minor = payload.rate_minor
    invoice.tax_minor = payload.tax_minor
    invoice.subtotal_minor = subtotal
    invoice.total_minor = total
    invoice.due_date = payload.due_date
    invoice.email_subject = (payload.email_subject or "").strip() or build_default_subject(invoice.invoice_number, invoice.client_name)
    invoice.email_body = (payload.email_body or "").strip() or build_default_email_body(
        invoice_number=invoice.invoice_number,
        client_name=invoice.client_name,
        description=invoice.description,
        total_minor=invoice.total_minor,
        currency=invoice.currency,
        due_date=invoice.due_date,
    )
    invoice.status = "draft"
    invoice.last_error = None

    if invoice.items:
        item = invoice.items[0]
        item.position = 1
        item.description = invoice.description
        item.details = invoice.details
        item.quantity = invoice.quantity
        item.rate_minor = invoice.rate_minor
        item.tax_minor = invoice.tax_minor
    else:
        db.add(FinanceInvoiceItem(
            invoice_id=invoice.id,
            position=1,
            description=invoice.description,
            details=invoice.details,
            quantity=invoice.quantity,
            rate_minor=invoice.rate_minor,
            tax_minor=invoice.tax_minor,
        ))

    log_finance_action(
        db,
        action="finance.invoice.edited",
        resource_type="finance_invoice",
        resource_id=invoice.id,
        actor_user_id=current.id,
        metadata={"invoice_number": invoice.invoice_number, "total_minor": invoice.total_minor, "due_date": invoice.due_date.isoformat()},
    )
    db.commit()
    return invoice_financial_out(_invoice(db, invoice.id))


@router.get("/invoices/{invoice_id}/activity")
def invoice_activity(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    invoice = _invoice(db, invoice_id)
    return {"invoice_number": invoice.invoice_number, "items": finance_activity(db, resource_type="finance_invoice", resource_id=invoice.id)}


@router.post("/reminders/process")
def process_reminders_now(current: User = Depends(require_platform_owner)):
    del current
    return {"sent": process_due_payment_reminders()}
