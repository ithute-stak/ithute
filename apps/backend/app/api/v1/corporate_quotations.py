from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceDocument, FinanceDocumentItem, User
from app.services.corporate_quotation import pack_metadata, render_corporate_quote_pdf, unpack_metadata
from app.services.finance_documents import next_document_number
from app.services.finance_mail import send_finance_message
from app.services.finance_invoices import money

router = APIRouter(prefix="/finance/corporate-quotations", tags=["finance-corporate-quotations"])


class CorporateQuotationCreate(BaseModel):
    client_name: str = Field(min_length=2, max_length=180)
    recipient_emails: list[EmailStr] = Field(min_length=1, max_length=10)
    client_address: str = Field(default="Maseru, Lesotho", max_length=500)
    mailbox_count: int = Field(default=20, ge=1, le=10000)
    storage_gb: int = Field(default=50, ge=1, le=10000)
    retail_per_mailbox_minor: int = Field(default=40000, ge=0, le=2_000_000_000)
    monthly_total_minor: int = Field(default=700000, ge=0, le=2_000_000_000)
    quarterly_total_minor: int = Field(default=1950000, ge=0, le=2_000_000_000)
    annual_total_minor: int = Field(default=7200000, ge=0, le=2_000_000_000)
    validity_days: int = Field(default=30, ge=1, le=180)
    notes: str = Field(default="", max_length=4000)
    prepared_by: str = Field(default="Koetlisi Theko", max_length=120)
    prepared_email: EmailStr = "thekoetlisi@ithute.co.ls"
    prepared_phone: str = Field(default="+266 5900 1394", max_length=80)


def _load(db: Session, quote_id: UUID) -> FinanceDocument | None:
    return db.scalar(select(FinanceDocument).options(selectinload(FinanceDocument.items)).where(FinanceDocument.id == quote_id))


def _out(row: FinanceDocument) -> dict:
    meta = unpack_metadata(row.notes)
    return {
        "id": str(row.id), "document_number": row.document_number, "client_name": row.client_name,
        "recipient_email": row.recipient_email, "recipient_emails": [row.recipient_email] + list(meta.get("recipient_cc") or []),
        "status": row.status, "mailbox_count": meta.get("mailbox_count"), "storage_gb": meta.get("storage_gb"),
        "monthly_total_minor": meta.get("monthly_total_minor"), "quarterly_total_minor": meta.get("quarterly_total_minor"),
        "annual_total_minor": meta.get("annual_total_minor"), "validity_days": meta.get("validity_days"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
    }


@router.get("")
def list_corporate_quotations(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceDocument).options(selectinload(FinanceDocument.items)).where(FinanceDocument.document_type == "quotation").order_by(FinanceDocument.created_at.desc()).limit(200)).all()
    return {"items": [_out(row) for row in rows if unpack_metadata(row.notes)]}


@router.post("", status_code=201)
def create_corporate_quotation(payload: CorporateQuotationCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    emails = [str(e).strip().lower() for e in payload.recipient_emails]
    retail_monthly = payload.mailbox_count * payload.retail_per_mailbox_minor
    meta = {
        "template": "imail-corporate-v1", "recipient_cc": emails[1:], "mailbox_count": payload.mailbox_count,
        "storage_gb": payload.storage_gb, "retail_monthly_minor": retail_monthly,
        "monthly_total_minor": payload.monthly_total_minor, "quarterly_total_minor": payload.quarterly_total_minor,
        "annual_total_minor": payload.annual_total_minor, "validity_days": payload.validity_days,
        "prepared_by": payload.prepared_by.strip(), "prepared_email": str(payload.prepared_email).lower(),
        "prepared_phone": payload.prepared_phone.strip(),
    }
    row = FinanceDocument(
        document_number=next_document_number(db, "quotation"), document_type="quotation", status="draft",
        client_name=payload.client_name.strip(), recipient_email=emails[0], client_address=payload.client_address.strip(),
        currency="LSL", subtotal_minor=payload.annual_total_minor, tax_minor=0, total_minor=payload.annual_total_minor,
        valid_until=date.today() + timedelta(days=payload.validity_days), payment_terms_days=0,
        notes=pack_metadata(meta, payload.notes), created_by_user_id=current.id,
    )
    db.add(row); db.flush()
    row.items.append(FinanceDocumentItem(
        position=1, description=f"iMail Corporate Email Hosting - {payload.mailbox_count} x {payload.storage_gb} GB",
        details=f"Recommended annual package; {payload.mailbox_count * payload.storage_gb} GB total allocated mailbox capacity",
        quantity=1, rate_minor=payload.annual_total_minor, tax_minor=0,
    ))
    db.commit(); db.refresh(row)
    return _out(_load(db, row.id) or row)


@router.get("/{quote_id}/pdf")
def corporate_quotation_pdf(quote_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = _load(db, quote_id)
    if row is None or not unpack_metadata(row.notes):
        raise HTTPException(status_code=404, detail="Corporate quotation not found")
    pdf = render_corporate_quote_pdf(row)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{row.document_number}.pdf"'})


@router.post("/{quote_id}/send")
def send_corporate_quotation(quote_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = _load(db, quote_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Corporate quotation not found")
    meta = unpack_metadata(row.notes)
    if not meta:
        raise HTTPException(status_code=409, detail="Document is not a corporate quotation")
    recipients = [row.recipient_email] + [str(x).strip().lower() for x in meta.get("recipient_cc", []) if str(x).strip()]
    pdf = render_corporate_quote_pdf(row)
    text = (
        f"Dear {row.client_name} Team,\n\nPlease find attached our detailed quotation for Ithute iMail Corporate Email Hosting. "
        f"The proposal covers {meta.get('mailbox_count')} professional email accounts with {meta.get('storage_gb')} GB per mailbox.\n\n"
        f"Recommended annual package: {money(int(meta.get('annual_total_minor') or row.total_minor), 'LSL')} per year.\n\n"
        "Kindly review the attached quotation and let us know which billing option is most suitable.\n\n"
        f"Kind regards,\n{meta.get('prepared_by') or 'Koetlisi Theko'}\nIthute Solutions / iMail\n"
        f"{meta.get('prepared_email') or 'thekoetlisi@ithute.co.ls'}\n{meta.get('prepared_phone') or '+266 5900 1394'}\nhttps://ithute.co.ls"
    )
    for recipient in recipients:
        send_finance_message(
            db, recipient=recipient, subject=f"Quotation for Corporate Email Hosting - {row.document_number}",
            text_body=text, html_body=text.replace("\n", "<br>"),
            attachment_filename=f"{row.document_number}.pdf", attachment_data=pdf,
        )
    from datetime import datetime, timezone
    row.status = "sent"; row.sent_at = datetime.now(timezone.utc); db.commit()
    return _out(_load(db, row.id) or row)
