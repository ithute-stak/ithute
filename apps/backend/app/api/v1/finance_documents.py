from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import (
    FinanceAuditEvent,
    FinanceClient,
    FinanceCommercialDocument,
    FinanceCommercialDocumentItem,
    FinanceInvoice,
    FinancePayment,
    User,
)
from app.services.finance_documents import (
    audit,
    convert_to_invoice,
    document_out,
    next_document_number,
    render_document_pdf,
    render_receipt_pdf,
    send_document,
)
from app.services.finance_ledger import invoice_financial_out

router = APIRouter(prefix="/finance/documents", tags=["finance-documents"])


class DocumentItemInput(BaseModel):
    description: str = Field(min_length=2, max_length=500)
    details: str = Field(default="", max_length=1200)
    quantity: int = Field(default=1, ge=1, le=10000)
    unit_rate_minor: int = Field(ge=0, le=2_000_000_000)
    tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)


class DocumentCreate(BaseModel):
    document_type: str = Field(pattern="^(quotation|proforma|credit_note)$")
    client_id: UUID | None = None
    source_invoice_id: UUID | None = None
    client_name: str = Field(min_length=2, max_length=180)
    recipient_email: EmailStr
    client_address: str = Field(default="", max_length=500)
    issue_date: date
    valid_until: date | None = None
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    notes: str = Field(default="", max_length=5000)
    items: list[DocumentItemInput] = Field(min_length=1, max_length=20)


class DocumentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|accepted|rejected|cancelled)$")


def _document(db: Session, document_id: UUID) -> FinanceCommercialDocument:
    row = db.scalar(
        select(FinanceCommercialDocument)
        .options(selectinload(FinanceCommercialDocument.items))
        .where(FinanceCommercialDocument.id == document_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    return row


@router.get("")
def list_documents(
    q: str | None = Query(default=None, max_length=160),
    document_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceCommercialDocument).options(selectinload(FinanceCommercialDocument.items)).order_by(FinanceCommercialDocument.created_at.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(FinanceCommercialDocument.document_number.ilike(term), FinanceCommercialDocument.client_name.ilike(term), FinanceCommercialDocument.recipient_email.ilike(term)))
    if document_type:
        stmt = stmt.where(FinanceCommercialDocument.document_type == document_type)
    if status:
        stmt = stmt.where(FinanceCommercialDocument.status == status)
    rows = db.scalars(stmt).unique().all()
    return {"items": [document_out(row) for row in rows], "total": len(rows)}


@router.post("", status_code=201)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    if payload.currency.strip().upper() != "LSL":
        raise HTTPException(status_code=422, detail="Finance documents currently use LSL")
    if payload.valid_until and payload.valid_until < payload.issue_date:
        raise HTTPException(status_code=422, detail="Valid-until date cannot be before the issue date")
    if payload.client_id and db.get(FinanceClient, payload.client_id) is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    if payload.source_invoice_id and db.get(FinanceInvoice, payload.source_invoice_id) is None:
        raise HTTPException(status_code=404, detail="Source invoice not found")

    subtotal = sum(item.quantity * item.unit_rate_minor for item in payload.items)
    tax = sum(item.tax_minor for item in payload.items)
    row = FinanceCommercialDocument(
        document_number=next_document_number(db, payload.document_type, payload.issue_date),
        document_type=payload.document_type,
        status="draft",
        client_id=payload.client_id,
        source_invoice_id=payload.source_invoice_id,
        client_name=payload.client_name.strip(),
        recipient_email=str(payload.recipient_email).lower(),
        client_address=payload.client_address.strip(),
        issue_date=payload.issue_date,
        valid_until=payload.valid_until,
        currency="LSL",
        subtotal_minor=subtotal,
        tax_minor=tax,
        total_minor=subtotal + tax,
        notes=payload.notes.strip(),
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    for position, item in enumerate(payload.items, start=1):
        line_subtotal = item.quantity * item.unit_rate_minor
        db.add(
            FinanceCommercialDocumentItem(
                document_id=row.id,
                position=position,
                description=item.description.strip(),
                details=item.details.strip(),
                quantity=item.quantity,
                unit_rate_minor=item.unit_rate_minor,
                tax_minor=item.tax_minor,
                line_subtotal_minor=line_subtotal,
                line_total_minor=line_subtotal + item.tax_minor,
            )
        )
    audit(db, entity_type="commercial_document", entity_id=row.id, action="created", summary=f"Created {row.document_type} {row.document_number}", actor_user_id=current.id)
    db.commit()
    return document_out(_document(db, row.id))


@router.get("/{document_id}")
def get_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return document_out(_document(db, document_id))


@router.get("/{document_id}/pdf")
def download_document_pdf(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = _document(db, document_id)
    pdf = render_document_pdf(row)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{row.document_number}.pdf"'})


@router.post("/{document_id}/send")
def send_document_endpoint(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = _document(db, document_id)
    if row.status in {"converted", "cancelled", "rejected"}:
        raise HTTPException(status_code=409, detail=f"Cannot send a {row.status} document")
    try:
        send_document(db, row)
        audit(db, entity_type="commercial_document", entity_id=row.id, action="sent", summary=f"Sent {row.document_number} to {row.recipient_email}", actor_user_id=current.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.get(FinanceCommercialDocument, document_id)
        if failed is not None:
            failed.last_error = str(exc)[:2000]
            db.commit()
        raise HTTPException(status_code=502, detail=f"Document email could not be sent: {str(exc)[:300]}") from exc
    return document_out(_document(db, document_id))


@router.patch("/{document_id}/status")
def update_document_status(document_id: UUID, payload: DocumentStatusUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = _document(db, document_id)
    if row.status == "converted":
        raise HTTPException(status_code=409, detail="Converted documents are locked")
    row.status = payload.status
    now = datetime.now(timezone.utc)
    if payload.status == "accepted":
        row.accepted_at = now
        row.rejected_at = None
    elif payload.status == "rejected":
        row.rejected_at = now
        row.accepted_at = None
    audit(db, entity_type="commercial_document", entity_id=row.id, action=f"status_{payload.status}", summary=f"{row.document_number} marked {payload.status}", actor_user_id=current.id)
    db.commit()
    return document_out(_document(db, document_id))


@router.post("/{document_id}/convert-to-invoice", status_code=201)
def convert_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = _document(db, document_id)
    try:
        invoice = convert_to_invoice(db, row, current.id)
        db.commit()
        db.refresh(invoice)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return invoice_financial_out(invoice)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = _document(db, document_id)
    if row.status not in {"draft", "rejected", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only draft, rejected or cancelled documents can be deleted")
    audit(db, entity_type="commercial_document", entity_id=row.id, action="deleted", summary=f"Deleted {row.document_number}", actor_user_id=current.id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/receipts/list/all")
def list_receipts(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.execute(
        select(FinancePayment, FinanceInvoice)
        .join(FinanceInvoice, FinanceInvoice.id == FinancePayment.invoice_id)
        .order_by(FinancePayment.payment_date.desc(), FinancePayment.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "client_name": invoice.client_name,
                "recipient_email": invoice.recipient_email,
                "payment_date": payment.payment_date.isoformat(),
                "amount_minor": payment.amount_minor,
                "method": payment.method,
                "reference": payment.reference,
            }
            for payment, invoice in rows
        ]
    }


@router.get("/receipts/{payment_id}/pdf")
def download_receipt(payment_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    payment = db.get(FinancePayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    invoice = db.get(FinanceInvoice, payment.invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf = render_receipt_pdf(payment, invoice)
    filename = f"Receipt-{invoice.invoice_number}-{payment.payment_date.isoformat()}.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/audit/list/all")
def list_audit_events(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    rows = db.scalars(select(FinanceAuditEvent).order_by(FinanceAuditEvent.created_at.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "action": row.action,
                "summary": row.summary,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
