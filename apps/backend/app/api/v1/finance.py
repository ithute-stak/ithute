from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import FinanceInvoice, FinanceSenderConfiguration, User
from app.services.finance_delivery import send_invoice
from app.services.finance_invoice_v2 import render_invoice_pdf
from app.services.finance_invoices import (
    build_default_email_body,
    build_default_subject,
    invoice_out,
    next_invoice_number,
)
from app.services.finance_mail import finance_sender_out, get_finance_sender_configuration, verify_finance_sender

router = APIRouter(prefix="/finance", tags=["finance"])


class FinanceInvoiceCreate(BaseModel):
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


class FinanceSenderUpdate(BaseModel):
    sender_email: EmailStr
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: str | None = Field(default=None, min_length=1, max_length=500)
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    security_mode: str = Field(default="starttls", max_length=20)


@router.get("/sender")
def get_finance_sender(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    return finance_sender_out(get_finance_sender_configuration(db))


@router.put("/sender")
def update_finance_sender(
    payload: FinanceSenderUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
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
def verify_finance_sender_endpoint(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
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
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    rows = db.scalars(select(FinanceInvoice).order_by(FinanceInvoice.created_at.desc()).limit(limit)).all()
    return {"items": [invoice_out(row) for row in rows], "total": len(rows)}


@router.post("/invoices", status_code=201)
def create_finance_invoice(
    payload: FinanceInvoiceCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    currency = payload.currency.strip().upper()
    if currency != "LSL":
        raise HTTPException(status_code=422, detail="Finance invoices currently use LSL")

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
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invoice number collision; please create the invoice again") from exc
    db.refresh(invoice)
    return invoice_out(invoice)


@router.get("/invoices/{invoice_id}")
def get_finance_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    invoice = db.get(FinanceInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice_out(invoice)


@router.get("/invoices/{invoice_id}/pdf")
def download_finance_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    invoice = db.get(FinanceInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf = render_invoice_pdf(invoice)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )


def _persist_send_failure(db: Session, invoice_id: UUID, error: Exception) -> None:
    db.rollback()
    failed = db.get(FinanceInvoice, invoice_id)
    if failed is None:
        return
    failed.status = "failed"
    failed.last_error = str(error)[:2000]
    db.commit()


@router.post("/invoices/{invoice_id}/send")
def send_finance_invoice(
    invoice_id: UUID,
    payload: SendInvoiceRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    invoice = db.get(FinanceInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == "sent" and not payload.resend:
        raise HTTPException(status_code=409, detail="Invoice has already been sent; explicitly request a resend if required")
    try:
        send_invoice(db, invoice)
        db.commit()
    except ValueError as exc:
        _persist_send_failure(db, invoice_id, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        _persist_send_failure(db, invoice_id, exc)
        raise HTTPException(status_code=502, detail=f"Invoice email could not be sent: {str(exc)[:300]}") from exc
    db.refresh(invoice)
    return invoice_out(invoice)
