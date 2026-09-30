from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceApprovalRequest, FinanceClient, FinanceGovernanceSetting, FinanceInvoice, User
from app.services.finance_audit import log_finance_action
from app.services.finance_governance import (
    approval_out,
    decide_invoice_approval,
    get_governance_setting,
    governance_out,
    invoice_requires_approval,
    request_invoice_approval,
)
from app.services.finance_mail import send_finance_message
from app.services.finance_statements import client_payment_behaviour, render_statement_pack, render_statement_pdf

router = APIRouter(prefix="/finance/governance", tags=["finance-governance"])


class GovernanceUpdate(BaseModel):
    approval_enabled: bool = True
    invoice_approval_threshold_minor: int = Field(ge=0, le=2_000_000_000)


class ApprovalRequestIn(BaseModel):
    note: str = Field(default="", max_length=2000)


class ApprovalDecisionIn(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=2000)


class StatementSendIn(BaseModel):
    client_ids: list[UUID] | None = Field(default=None, max_length=500)
    as_of: date | None = None
    only_with_balance: bool = True


def _invoice(db: Session, invoice_id: UUID) -> FinanceInvoice:
    row = db.scalar(
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items))
        .where(FinanceInvoice.id == invoice_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return row


def _client_invoices(db: Session, client_id: UUID, as_of: date | None = None) -> list[FinanceInvoice]:
    stmt = (
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items))
        .where(FinanceInvoice.client_id == client_id)
        .order_by(FinanceInvoice.created_at.asc())
    )
    rows = list(db.scalars(stmt).all())
    if as_of is not None:
        rows = [row for row in rows if not row.created_at or row.created_at.date() <= as_of]
    return rows


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    row = get_governance_setting(db)
    db.commit(); db.refresh(row)
    return governance_out(row)


@router.put("/settings")
def update_settings(payload: GovernanceUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = get_governance_setting(db)
    row.approval_enabled = payload.approval_enabled
    row.invoice_approval_threshold_minor = payload.invoice_approval_threshold_minor
    row.updated_by_user_id = current.id
    log_finance_action(db, action="finance.governance.updated", resource_type="finance_governance", resource_id=row.id, actor_user_id=current.id, metadata={"approval_enabled": row.approval_enabled, "invoice_approval_threshold_minor": row.invoice_approval_threshold_minor})
    db.commit(); db.refresh(row)
    return governance_out(row)


@router.get("/approvals")
def list_approvals(
    status: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    stmt = select(FinanceApprovalRequest).order_by(FinanceApprovalRequest.requested_at.desc())
    if status:
        stmt = stmt.where(FinanceApprovalRequest.status == status.strip().lower())
    rows = list(db.scalars(stmt).all())
    invoices = {invoice.id: invoice for invoice in db.scalars(select(FinanceInvoice).where(FinanceInvoice.id.in_([row.resource_id for row in rows] or [UUID(int=0)]))).all()}
    return {"items": [approval_out(row, invoices.get(row.resource_id)) for row in rows], "total": len(rows)}


@router.post("/invoices/{invoice_id}/approval")
def request_approval(invoice_id: UUID, payload: ApprovalRequestIn, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    invoice = _invoice(db, invoice_id)
    if invoice.status in {"paid", "cancelled", "credited"}:
        raise HTTPException(status_code=409, detail=f"Invoice is {invoice.status} and cannot enter approval")
    row = request_invoice_approval(db, invoice, user_id=current.id, note=payload.note)
    log_finance_action(db, action="finance.invoice.approval_requested", resource_type="finance_invoice", resource_id=invoice.id, actor_user_id=current.id, metadata={"invoice_number": invoice.invoice_number, "total_minor": invoice.total_minor, "required_by_threshold": invoice_requires_approval(db, invoice)})
    db.commit(); db.refresh(row)
    return approval_out(row, invoice)


@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: UUID, payload: ApprovalDecisionIn, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(FinanceApprovalRequest, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    invoice = _invoice(db, row.resource_id)
    decide_invoice_approval(db, row, approved=payload.approved, user_id=current.id, note=payload.note)
    log_finance_action(db, action="finance.invoice.approved" if payload.approved else "finance.invoice.rejected", resource_type="finance_invoice", resource_id=invoice.id, actor_user_id=current.id, metadata={"invoice_number": invoice.invoice_number, "approval_id": str(row.id), "note": payload.note})
    db.commit(); db.refresh(row)
    return approval_out(row, invoice)


@router.get("/clients/{client_id}/behaviour")
def client_behaviour(client_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    return client_payment_behaviour(client, _client_invoices(db, client.id))


@router.get("/clients/{client_id}/statement.pdf")
def client_statement_pdf(
    client_id: UUID,
    as_of: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    pdf = render_statement_pdf(client, _client_invoices(db, client.id, as_of), as_of=as_of)
    filename = f"Statement-{client.name}-{(as_of or date.today()).isoformat()}.pdf".replace(" ", "-")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/statement-pack.zip")
def statement_pack(
    as_of: date | None = Query(default=None),
    only_with_balance: bool = Query(default=True),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    clients = list(db.scalars(select(FinanceClient).where(FinanceClient.active.is_(True)).order_by(FinanceClient.name.asc())).all())
    pairs: list[tuple[FinanceClient, list[FinanceInvoice]]] = []
    for client in clients:
        invoices = _client_invoices(db, client.id, as_of)
        if only_with_balance:
            behaviour = client_payment_behaviour(client, invoices, today=as_of or date.today())
            if behaviour["current_exposure_minor"] <= 0:
                continue
        pairs.append((client, invoices))
    payload = render_statement_pack(pairs, as_of=as_of)
    filename = f"ithute-statement-pack-{(as_of or date.today()).isoformat()}.zip"
    return Response(payload, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/statements/send")
def send_statements(payload: StatementSendIn, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    stmt = select(FinanceClient).where(FinanceClient.active.is_(True)).order_by(FinanceClient.name.asc())
    if payload.client_ids:
        stmt = stmt.where(FinanceClient.id.in_(payload.client_ids))
    clients = list(db.scalars(stmt).all())
    sent: list[str] = []; skipped: list[dict] = []; failed: list[dict] = []
    statement_date = payload.as_of or date.today()
    for client in clients:
        invoices = _client_invoices(db, client.id, payload.as_of)
        behaviour = client_payment_behaviour(client, invoices, today=statement_date)
        if payload.only_with_balance and behaviour["current_exposure_minor"] <= 0:
            skipped.append({"client_id": str(client.id), "reason": "No outstanding balance"}); continue
        if not invoices:
            skipped.append({"client_id": str(client.id), "reason": "No invoices"}); continue
        pdf = render_statement_pdf(client, invoices, as_of=statement_date)
        subject = f"Ithute statement of account — {statement_date.strftime('%B %Y')}"
        body = f"Dear {client.name},\n\nPlease find attached your Ithute statement of account as at {statement_date.strftime('%d %B %Y')}.\n\nOutstanding balance: M {behaviour['current_exposure_minor'] / 100:,.2f}.\n\nPlease use the invoice number or your client name as the payment reference.\n\nRegards,\nIthute Finance"
        try:
            send_finance_message(db, recipient=client.email, subject=subject, text_body=body, html_body=None, attachment_filename=f"Statement-{statement_date.isoformat()}.pdf", attachment_data=pdf)
            sent.append(str(client.id))
            log_finance_action(db, action="finance.statement.sent", resource_type="finance_client", resource_id=client.id, actor_user_id=current.id, metadata={"recipient": client.email, "as_of": statement_date.isoformat(), "balance_minor": behaviour["current_exposure_minor"]})
            db.commit()
        except Exception as exc:
            db.rollback(); failed.append({"client_id": str(client.id), "error": str(exc)[:300]})
    return {"sent": sent, "skipped": skipped, "failed": failed}
