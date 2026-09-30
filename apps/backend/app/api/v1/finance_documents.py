from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import (
    FinanceClient,
    FinanceCreditNote,
    FinanceDocument,
    FinanceDocumentItem,
    FinanceInvoice,
    User,
)
from app.services.finance_documents import (
    convert_document_to_invoice,
    credit_note_out,
    document_out,
    load_credit,
    load_document,
    load_payment,
    next_credit_number,
    next_document_number,
    render_credit_note_pdf,
    render_document_pdf,
    render_receipt_pdf,
    send_document,
)
from app.services.finance_ledger import invoice_financial_out, sync_invoice_payment_status

router = APIRouter(prefix="/finance", tags=["finance-documents"])


class LineItemInput(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    details: str = Field(default="", max_length=1200)
    quantity: int = Field(default=1, ge=1, le=10000)
    rate_minor: int = Field(ge=0, le=2_000_000_000)
    tax_minor: int = Field(default=0, ge=0, le=2_000_000_000)


class DocumentCreate(BaseModel):
    document_type: str = Field(pattern="^(quotation|proforma)$")
    client_id: UUID | None = None
    client_name: str = Field(min_length=2, max_length=180)
    recipient_email: EmailStr
    client_address: str = Field(default="", max_length=500)
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    valid_until: date | None = None
    payment_terms_days: int = Field(default=7, ge=0, le=365)
    notes: str = Field(default="", max_length=5000)
    items: list[LineItemInput] = Field(min_length=1, max_length=8)


class DocumentUpdate(DocumentCreate):
    pass


class DocumentStatusInput(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")


class CreditNoteCreate(BaseModel):
    amount_minor: int = Field(gt=0, le=2_000_000_000)
    reason: str = Field(min_length=2, max_length=1000)


def _client(db: Session, client_id: UUID | None) -> FinanceClient | None:
    if client_id is None:
        return None
    row = db.get(FinanceClient, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    return row


def _totals(items: list[LineItemInput]) -> tuple[int, int, int]:
    subtotal = sum(item.quantity * item.rate_minor for item in items)
    tax = sum(item.tax_minor for item in items)
    return subtotal, tax, subtotal + tax


def _replace_items(db: Session, document: FinanceDocument, items: list[LineItemInput]) -> None:
    document.items.clear()
    db.flush()
    for position, item in enumerate(items, start=1):
        document.items.append(FinanceDocumentItem(
            position=position,
            description=item.description.strip(),
            details=item.details.strip(),
            quantity=item.quantity,
            rate_minor=item.rate_minor,
            tax_minor=item.tax_minor,
        ))


@router.get("/documents")
def list_documents(
    q: str | None = Query(default=None, max_length=160),
    document_type: str | None = Query(default=None, max_length=30),
    status: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceDocument).options(selectinload(FinanceDocument.items)).order_by(FinanceDocument.created_at.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(FinanceDocument.document_number.ilike(term), FinanceDocument.client_name.ilike(term), FinanceDocument.recipient_email.ilike(term)))
    if document_type:
        stmt = stmt.where(FinanceDocument.document_type == document_type.strip().lower())
    if status:
        stmt = stmt.where(FinanceDocument.status == status.strip().lower())
    rows = db.scalars(stmt.limit(limit)).all()
    return {"items": [document_out(row) for row in rows], "total": len(rows)}


@router.post("/documents", status_code=201)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    currency = payload.currency.strip().upper()
    if currency != "LSL":
        raise HTTPException(status_code=422, detail="Finance documents currently use LSL")
    _client(db, payload.client_id)
    subtotal, tax, total = _totals(payload.items)
    document_type = payload.document_type.strip().lower()
    row = FinanceDocument(
        document_number=next_document_number(db, document_type),
        document_type=document_type,
        status="draft",
        client_id=payload.client_id,
        client_name=payload.client_name.strip(),
        recipient_email=str(payload.recipient_email).lower(),
        client_address=payload.client_address.strip(),
        currency=currency,
        subtotal_minor=subtotal,
        tax_minor=tax,
        total_minor=total,
        valid_until=payload.valid_until,
        payment_terms_days=payload.payment_terms_days,
        notes=payload.notes.strip(),
        created_by_user_id=current.id,
    )
    db.add(row); db.flush()
    _replace_items(db, row, payload.items)
    db.commit()
    return document_out(load_document(db, row.id))


@router.get("/documents/{document_id}")
def get_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    return document_out(row)


@router.put("/documents/{document_id}")
def update_document(document_id: UUID, payload: DocumentUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    if row.status == "converted":
        raise HTTPException(status_code=409, detail="Converted documents are locked")
    if row.document_type != payload.document_type.strip().lower():
        raise HTTPException(status_code=409, detail="Document type cannot be changed after numbering; create a new document instead")
    _client(db, payload.client_id)
    subtotal, tax, total = _totals(payload.items)
    row.client_id = payload.client_id
    row.client_name = payload.client_name.strip()
    row.recipient_email = str(payload.recipient_email).lower()
    row.client_address = payload.client_address.strip()
    row.currency = payload.currency.strip().upper()
    row.subtotal_minor = subtotal
    row.tax_minor = tax
    row.total_minor = total
    row.valid_until = payload.valid_until
    row.payment_terms_days = payload.payment_terms_days
    row.notes = payload.notes.strip()
    _replace_items(db, row, payload.items)
    db.commit()
    return document_out(load_document(db, row.id))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    if row.status == "converted":
        raise HTTPException(status_code=409, detail="Converted documents cannot be deleted")
    db.delete(row); db.commit(); return Response(status_code=204)


@router.get("/documents/{document_id}/pdf")
def document_pdf(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    return Response(render_document_pdf(row), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{row.document_number}.pdf"'})


@router.post("/documents/{document_id}/send")
def send_document_endpoint(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    if row.status == "converted":
        raise HTTPException(status_code=409, detail="Converted documents are locked")
    try:
        send_document(db, row); db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback(); raise HTTPException(status_code=502, detail=f"Document email could not be sent: {str(exc)[:300]}") from exc
    return document_out(load_document(db, row.id))


@router.post("/documents/{document_id}/status")
def set_document_status(document_id: UUID, payload: DocumentStatusInput, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    if row.status == "converted":
        raise HTTPException(status_code=409, detail="Converted documents are locked")
    now = datetime.now(timezone.utc)
    row.status = payload.status
    row.accepted_at = now if payload.status == "accepted" else None
    row.rejected_at = now if payload.status == "rejected" else None
    db.commit()
    return document_out(load_document(db, row.id))


@router.post("/documents/{document_id}/convert", status_code=201)
def convert_document(document_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = load_document(db, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance document not found")
    try:
        invoice = convert_document_to_invoice(db, row, user_id=current.id)
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
    invoice = db.scalar(
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.items), selectinload(FinanceInvoice.credit_notes))
        .where(FinanceInvoice.id == invoice.id)
    )
    return invoice_financial_out(invoice)


@router.get("/payments/{payment_id}/receipt.pdf")
def payment_receipt(payment_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    payment = load_payment(db, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    filename = f"Receipt-{payment.invoice.invoice_number}-{payment.payment_date.isoformat()}.pdf"
    return Response(render_receipt_pdf(payment), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/credit-notes")
def list_credit_notes(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceCreditNote).options(selectinload(FinanceCreditNote.invoice)).order_by(FinanceCreditNote.created_at.desc())).all()
    return {"items": [credit_note_out(row) | {"invoice_number": row.invoice.invoice_number, "client_name": row.invoice.client_name} for row in rows], "total": len(rows)}


@router.post("/invoices/{invoice_id}/credit-notes", status_code=201)
def create_credit_note(invoice_id: UUID, payload: CreditNoteCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    invoice = db.scalar(
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes))
        .where(FinanceInvoice.id == invoice_id)
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot issue a credit note against a cancelled invoice")
    credited = sum(note.amount_minor for note in invoice.credit_notes)
    remaining_creditable = max(0, invoice.total_minor - credited)
    if payload.amount_minor > remaining_creditable:
        raise HTTPException(status_code=422, detail="Credit amount cannot exceed the uncredited invoice total")
    row = FinanceCreditNote(
        credit_number=next_credit_number(db),
        invoice_id=invoice.id,
        amount_minor=payload.amount_minor,
        reason=payload.reason.strip(),
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    sync_invoice_payment_status(invoice)
    db.commit()
    db.refresh(row)
    return credit_note_out(row)


@router.get("/credit-notes/{credit_id}/pdf")
def credit_note_pdf(credit_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = load_credit(db, credit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Credit note not found")
    return Response(render_credit_note_pdf(row), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{row.credit_number}.pdf"'})
