from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import (
    FinanceClient,
    FinanceInvoice,
    FinanceInvoiceItem,
    FinanceInvoiceSchedule,
    FinancePayment,
    FinanceSenderConfiguration,
    User,
)
from app.services.finance_delivery import send_invoice
from app.services.finance_governance import FinanceApprovalRequiredError
from app.services.finance_invoice_multi import render_invoice_pdf
from app.services.finance_invoices import build_default_email_body, build_default_subject, next_invoice_number
from app.services.finance_ledger import (
    adjusted_total_minor,
    client_out,
    dashboard_out,
    invoice_financial_out,
    payment_out,
    sync_invoice_payment_status,
)
from app.services.finance_mail import finance_sender_out, get_finance_sender_configuration, verify_finance_sender
from app.services.finance_recurring import process_due_finance_schedules, schedule_out

router = APIRouter(prefix="/finance", tags=["finance"])


class FinanceInvoiceCreate(BaseModel):
    client_id: UUID | None = None
    client_name: str = Field(min_length=2, max_length=180)
    recipient_email: EmailStr
    client_address: str = Field(default="", max_length=500)
    description: str = Field(min_length=2, max_length=500)
    details: str = Field(default="", max_length=1200)
    service_period: str = Field(default="", max_length=160)
    quantity: int = Field(default=1, ge=1, le=10000)
    rate_minor: int = Field(ge=0, le=2_000_000_000)
    tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    due_date: date
    email_subject: str | None = Field(default=None, max_length=300)
    email_body: str | None = Field(default=None, max_length=10000)


class SendInvoiceRequest(BaseModel):
    resend: bool = False


class FinanceScheduleCreate(BaseModel):
    client_id: UUID | None = None
    client_name: str = Field(min_length=2, max_length=180)
    recipient_email: EmailStr
    client_address: str = Field(default="", max_length=500)
    description: str = Field(min_length=2, max_length=500)
    details: str = Field(default="", max_length=1200)
    quantity: int = Field(default=1, ge=1, le=10000)
    rate_minor: int = Field(ge=0, le=2_000_000_000)
    tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    send_day: int = Field(ge=1, le=31)
    due_days: int = Field(default=7, ge=0, le=365)


class FinanceScheduleUpdate(BaseModel):
    enabled: bool


class FinanceClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=80)
    default_service: str = Field(default="", max_length=500)
    default_details: str = Field(default="", max_length=1200)
    default_quantity: int = Field(default=1, ge=1, le=10000)
    default_rate_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    default_tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    payment_terms_days: int = Field(default=7, ge=0, le=365)
    active: bool = True
    notes: str = Field(default="", max_length=5000)


class FinanceClientUpdate(FinanceClientCreate):
    pass


class FinancePaymentCreate(BaseModel):
    amount_minor: int = Field(gt=0, le=2_000_000_000)
    payment_date: date
    method: str = Field(default="bank_transfer", min_length=2, max_length=80)
    reference: str = Field(default="", max_length=180)
    note: str = Field(default="", max_length=1000)


class FinanceSenderUpdate(BaseModel):
    sender_email: EmailStr
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: str | None = Field(default=None, min_length=1, max_length=500)
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    security_mode: str = Field(default="starttls", max_length=20)


def _invoice(db: Session, invoice_id: UUID) -> FinanceInvoice:
    invoice = db.scalar(
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.items),
            selectinload(FinanceInvoice.credit_notes),
        )
        .where(FinanceInvoice.id == invoice_id)
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _client(db: Session, client_id: UUID) -> FinanceClient:
    row = db.get(FinanceClient, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    return row


@router.get("/dashboard")
def get_finance_dashboard(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return dashboard_out(db)


@router.get("/clients")
def list_finance_clients(
    q: str | None = Query(default=None, max_length=160),
    active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceClient).order_by(FinanceClient.name.asc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(FinanceClient.name.ilike(term), FinanceClient.email.ilike(term), FinanceClient.phone.ilike(term)))
    if active is not None:
        stmt = stmt.where(FinanceClient.active.is_(active))
    rows = db.scalars(stmt).all()
    return {"items": [client_out(row) for row in rows], "total": len(rows)}


@router.post("/clients", status_code=201)
def create_finance_client(
    payload: FinanceClientCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = FinanceClient(
        name=payload.name.strip(),
        email=str(payload.email).lower(),
        address=payload.address.strip(),
        phone=payload.phone.strip(),
        default_service=payload.default_service.strip(),
        default_details=payload.default_details.strip(),
        default_quantity=payload.default_quantity,
        default_rate_minor=payload.default_rate_minor,
        default_tax_minor=payload.default_tax_minor,
        payment_terms_days=payload.payment_terms_days,
        active=payload.active,
        notes=payload.notes.strip(),
        created_by_user_id=current.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return client_out(row)


@router.get("/clients/{client_id}")
def get_finance_client(client_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = _client(db, client_id)
    invoices = db.scalars(
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.items),
            selectinload(FinanceInvoice.credit_notes),
        )
        .where(FinanceInvoice.client_id == row.id)
        .order_by(FinanceInvoice.created_at.desc())
    ).all()
    data = client_out(row)
    data["invoices"] = [invoice_financial_out(invoice) for invoice in invoices]
    data["outstanding_minor"] = sum(item["outstanding_minor"] for item in data["invoices"] if item["status"] != "cancelled")
    return data


@router.put("/clients/{client_id}")
def update_finance_client(
    client_id: UUID,
    payload: FinanceClientUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    row = _client(db, client_id)
    row.name = payload.name.strip()
    row.email = str(payload.email).lower()
    row.address = payload.address.strip()
    row.phone = payload.phone.strip()
    row.default_service = payload.default_service.strip()
    row.default_details = payload.default_details.strip()
    row.default_quantity = payload.default_quantity
    row.default_rate_minor = payload.default_rate_minor
    row.default_tax_minor = payload.default_tax_minor
    row.payment_terms_days = payload.payment_terms_days
    row.active = payload.active
    row.notes = payload.notes.strip()
    db.commit()
    db.refresh(row)
    return client_out(row)


@router.delete("/clients/{client_id}", status_code=204)
def delete_finance_client(client_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = _client(db, client_id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/sender")
def get_finance_sender(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return finance_sender_out(get_finance_sender_configuration(db))


@router.put("/sender")
def update_finance_sender(payload: FinanceSenderUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    mode = payload.security_mode.strip().lower()
    if mode not in {"starttls", "ssl", "plain"}:
        raise HTTPException(status_code=422, detail="Security mode must be starttls, ssl or plain")
    host = payload.smtp_host.strip()
    username = (payload.smtp_username or "").strip() or str(payload.sender_email).lower()
    sender_email = str(payload.sender_email).lower()
    if any(ch.isspace() for ch in host):
        raise HTTPException(status_code=422, detail="SMTP host must not contain spaces")

    config = get_finance_sender_configuration(db)
    password_changed = bool(payload.smtp_password)
    if config is None:
        if not payload.smtp_password:
            raise HTTPException(status_code=422, detail="SMTP password is required when configuring the sender")
        config = FinanceSenderConfiguration(
            sender_email=sender_email,
            smtp_username=username,
            smtp_password_encrypted=encrypt_secret(payload.smtp_password),
            smtp_host=host,
            smtp_port=payload.smtp_port,
            security_mode=mode,
            created_by_user_id=current.id,
            updated_by_user_id=current.id,
        )
        db.add(config)
    else:
        changed = any((
            config.sender_email != sender_email,
            config.smtp_username != username,
            config.smtp_host != host,
            config.smtp_port != payload.smtp_port,
            config.security_mode != mode,
            password_changed,
        ))
        config.sender_email = sender_email
        config.smtp_username = username
        config.smtp_host = host
        config.smtp_port = payload.smtp_port
        config.security_mode = mode
        config.updated_by_user_id = current.id
        if payload.smtp_password:
            config.smtp_password_encrypted = encrypt_secret(payload.smtp_password)
        if changed:
            config.verified_at = None
            config.last_verification_error = None
    db.commit()
    db.refresh(config)
    return finance_sender_out(config)


@router.post("/sender/verify")
def verify_finance_sender_endpoint(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    config = get_finance_sender_configuration(db)
    if config is None:
        raise HTTPException(status_code=409, detail="Configure the Finance sending email first")
    try:
        verify_finance_sender(config)
        db.commit()
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=422, detail=f"SMTP verification failed: {str(exc)[:300]}") from exc
    db.refresh(config)
    return finance_sender_out(config)


@router.get("/invoices")
def list_finance_invoices(
    limit: int = Query(default=100, ge=1, le=300),
    q: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, max_length=30),
    client_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = (
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.items),
            selectinload(FinanceInvoice.credit_notes),
        )
        .order_by(FinanceInvoice.created_at.desc())
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                FinanceInvoice.invoice_number.ilike(term),
                FinanceInvoice.client_name.ilike(term),
                FinanceInvoice.recipient_email.ilike(term),
                FinanceInvoice.description.ilike(term),
            )
        )
    if client_id is not None:
        stmt = stmt.where(FinanceInvoice.client_id == client_id)
    rows = db.scalars(stmt.limit(limit)).all()
    items = [invoice_financial_out(row) for row in rows]
    if status and status.strip():
        wanted = status.strip().lower()
        items = [item for item in items if item["status"] == wanted]
    return {"items": items, "total": len(items)}


@router.post("/invoices", status_code=201)
def create_finance_invoice(payload: FinanceInvoiceCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    currency = payload.currency.strip().upper()
    if currency != "LSL":
        raise HTTPException(status_code=422, detail="Finance invoices currently use LSL")
    if payload.client_id is not None:
        _client(db, payload.client_id)

    subtotal_minor = payload.quantity * payload.rate_minor
    total_minor = subtotal_minor + payload.tax_minor
    invoice_number = next_invoice_number(db)
    subject = (payload.email_subject or "").strip() or build_default_subject(invoice_number, payload.client_name.strip())
    body = (payload.email_body or "").strip() or build_default_email_body(
        invoice_number=invoice_number,
        client_name=payload.client_name.strip(),
        description=payload.description.strip(),
        total_minor=total_minor,
        currency=currency,
        due_date=payload.due_date,
    )

    invoice = FinanceInvoice(
        invoice_number=invoice_number,
        client_id=payload.client_id,
        client_name=payload.client_name.strip(),
        recipient_email=str(payload.recipient_email).lower(),
        client_address=payload.client_address.strip(),
        description=payload.description.strip(),
        details=payload.details.strip(),
        service_period=payload.service_period.strip(),
        quantity=payload.quantity,
        rate_minor=payload.rate_minor,
        tax_minor=payload.tax_minor,
        subtotal_minor=subtotal_minor,
        total_minor=total_minor,
        currency=currency,
        due_date=payload.due_date,
        status="draft",
        email_subject=subject,
        email_body=body,
        created_by_user_id=current.id,
    )
    db.add(invoice)
    try:
        db.flush()
        db.add(FinanceInvoiceItem(
            invoice_id=invoice.id,
            position=1,
            description=payload.description.strip(),
            details=payload.details.strip(),
            quantity=payload.quantity,
            rate_minor=payload.rate_minor,
            tax_minor=payload.tax_minor,
        ))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invoice number collision; please create the invoice again") from exc
    return invoice_financial_out(_invoice(db, invoice.id))


@router.get("/invoices/{invoice_id}")
def get_finance_invoice(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return invoice_financial_out(_invoice(db, invoice_id))


@router.delete("/invoices/{invoice_id}", status_code=204)
def delete_finance_invoice(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = _invoice(db, invoice_id)
    db.delete(invoice)
    db.commit()
    return Response(status_code=204)


@router.post("/invoices/{invoice_id}/cancel")
def cancel_finance_invoice(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = _invoice(db, invoice_id)
    if invoice.status in {"paid", "credited"}:
        raise HTTPException(status_code=409, detail="A settled invoice cannot be cancelled; use the credit-note record and audit trail instead")
    invoice.status = "cancelled"
    invoice.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return invoice_financial_out(_invoice(db, invoice_id))


@router.get("/invoices/{invoice_id}/pdf")
def download_finance_invoice_pdf(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = _invoice(db, invoice_id)
    pdf = render_invoice_pdf(invoice)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'})


def _persist_send_failure(db: Session, invoice_id: UUID, error: Exception) -> None:
    db.rollback()
    failed = db.get(FinanceInvoice, invoice_id)
    if failed is None:
        return
    failed.status = "failed"
    failed.last_error = str(error)[:2000]
    db.commit()


@router.post("/invoices/{invoice_id}/send")
def send_finance_invoice(invoice_id: UUID, payload: SendInvoiceRequest, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = _invoice(db, invoice_id)
    if invoice.status in {"paid", "cancelled", "credited"}:
        raise HTTPException(status_code=409, detail=f"Invoice is {invoice.status} and cannot be sent")
    if invoice.status == "sent" and not payload.resend:
        raise HTTPException(status_code=409, detail="Invoice has already been sent; explicitly request a resend if required")
    try:
        send_invoice(db, invoice)
        db.commit()
    except FinanceApprovalRequiredError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        _persist_send_failure(db, invoice_id, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        _persist_send_failure(db, invoice_id, exc)
        raise HTTPException(status_code=502, detail=f"Invoice email could not be sent: {str(exc)[:300]}") from exc
    return invoice_financial_out(_invoice(db, invoice_id))


@router.get("/invoices/{invoice_id}/payments")
def list_invoice_payments(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = _invoice(db, invoice_id)
    return {"items": [payment_out(row) for row in invoice.payments], "total": len(invoice.payments)}


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_invoice_payment(
    invoice_id: UUID,
    payload: FinancePaymentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    invoice = _invoice(db, invoice_id)
    if invoice.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot record a payment against a cancelled invoice")
    already_paid = sum(payment.amount_minor for payment in invoice.payments)
    outstanding = max(0, adjusted_total_minor(invoice) - already_paid)
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="Invoice is already fully settled")
    if payload.amount_minor > outstanding:
        raise HTTPException(status_code=422, detail=f"Payment exceeds outstanding balance of {outstanding} minor units")
    payment = FinancePayment(
        invoice_id=invoice.id,
        amount_minor=payload.amount_minor,
        payment_date=payload.payment_date,
        method=payload.method.strip().lower(),
        reference=payload.reference.strip(),
        note=payload.note.strip(),
        recorded_by_user_id=current.id,
    )
    db.add(payment)
    db.flush()
    sync_invoice_payment_status(invoice)
    db.commit()
    db.refresh(payment)
    return {"payment": payment_out(payment), "invoice": invoice_financial_out(_invoice(db, invoice_id))}


@router.delete("/payments/{payment_id}", status_code=204)
def delete_finance_payment(payment_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    payment = db.get(FinancePayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    invoice_id = payment.invoice_id
    db.delete(payment)
    db.flush()
    invoice = _invoice(db, invoice_id)
    sync_invoice_payment_status(invoice)
    db.commit()
    return Response(status_code=204)


@router.get("/schedules")
def list_finance_schedules(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceInvoiceSchedule).order_by(FinanceInvoiceSchedule.created_at.desc())).all()
    return {"items": [schedule_out(row) for row in rows], "total": len(rows)}


@router.post("/schedules", status_code=201)
def create_finance_schedule(payload: FinanceScheduleCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    currency = payload.currency.strip().upper()
    if currency != "LSL":
        raise HTTPException(status_code=422, detail="Finance invoices currently use LSL")
    if payload.client_id is not None:
        _client(db, payload.client_id)
    row = FinanceInvoiceSchedule(
        client_id=payload.client_id,
        client_name=payload.client_name.strip(),
        recipient_email=str(payload.recipient_email).lower(),
        client_address=payload.client_address.strip(),
        description=payload.description.strip(),
        details=payload.details.strip(),
        quantity=payload.quantity,
        rate_minor=payload.rate_minor,
        tax_minor=payload.tax_minor,
        currency=currency,
        send_day=payload.send_day,
        due_days=payload.due_days,
        enabled=True,
        created_by_user_id=current.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schedule_out(row)


@router.patch("/schedules/{schedule_id}")
def update_finance_schedule(schedule_id: UUID, payload: FinanceScheduleUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = db.get(FinanceInvoiceSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice schedule not found")
    row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return schedule_out(row)


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_finance_schedule(schedule_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = db.get(FinanceInvoiceSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice schedule not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post("/schedules/process")
def process_finance_schedules_now(current: User = Depends(require_platform_owner)):
    del current
    return {"sent": process_due_finance_schedules()}
