from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinanceApprovalRequest, FinanceGovernanceSetting, FinanceInvoice


def get_governance_setting(db: Session) -> FinanceGovernanceSetting:
    row = db.scalar(select(FinanceGovernanceSetting).order_by(FinanceGovernanceSetting.created_at.asc()).limit(1))
    if row is None:
        row = FinanceGovernanceSetting()
        db.add(row)
        db.flush()
    return row


def governance_out(row: FinanceGovernanceSetting) -> dict:
    return {
        "id": str(row.id),
        "approval_enabled": row.approval_enabled,
        "invoice_approval_threshold_minor": row.invoice_approval_threshold_minor,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def approval_out(row: FinanceApprovalRequest, invoice: FinanceInvoice | None = None) -> dict:
    data = {
        "id": str(row.id),
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id),
        "status": row.status,
        "request_note": row.request_note,
        "decision_note": row.decision_note,
        "requested_by_user_id": str(row.requested_by_user_id) if row.requested_by_user_id else None,
        "decided_by_user_id": str(row.decided_by_user_id) if row.decided_by_user_id else None,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }
    if invoice is not None:
        data["invoice"] = {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "client_name": invoice.client_name,
            "recipient_email": invoice.recipient_email,
            "total_minor": invoice.total_minor,
            "status": invoice.status,
            "due_date": invoice.due_date.isoformat(),
        }
    return data


def invoice_requires_approval(db: Session, invoice: FinanceInvoice) -> bool:
    setting = get_governance_setting(db)
    return bool(setting.approval_enabled and invoice.total_minor >= setting.invoice_approval_threshold_minor)


def invoice_approval(db: Session, invoice_id) -> FinanceApprovalRequest | None:
    return db.scalar(
        select(FinanceApprovalRequest).where(
            FinanceApprovalRequest.resource_type == "invoice",
            FinanceApprovalRequest.resource_id == invoice_id,
        )
    )


def ensure_invoice_approved_for_send(db: Session, invoice: FinanceInvoice) -> None:
    if not invoice_requires_approval(db, invoice):
        return
    approval = invoice_approval(db, invoice.id)
    if approval is None:
        raise ValueError(
            f"Invoice {invoice.invoice_number} requires approval before sending because it exceeds the configured approval threshold"
        )
    if approval.status != "approved":
        raise ValueError(
            f"Invoice {invoice.invoice_number} approval status is {approval.status}; it cannot be sent until approved"
        )


def request_invoice_approval(db: Session, invoice: FinanceInvoice, *, user_id, note: str = "") -> FinanceApprovalRequest:
    row = invoice_approval(db, invoice.id)
    if row is None:
        row = FinanceApprovalRequest(
            resource_type="invoice",
            resource_id=invoice.id,
            status="pending",
            request_note=note.strip(),
            requested_by_user_id=user_id,
        )
        db.add(row)
    else:
        row.status = "pending"
        row.request_note = note.strip()
        row.decision_note = ""
        row.requested_by_user_id = user_id
        row.decided_by_user_id = None
        row.requested_at = datetime.now(timezone.utc)
        row.decided_at = None
    db.flush()
    return row


def decide_invoice_approval(db: Session, row: FinanceApprovalRequest, *, approved: bool, user_id, note: str = "") -> None:
    row.status = "approved" if approved else "rejected"
    row.decision_note = note.strip()
    row.decided_by_user_id = user_id
    row.decided_at = datetime.now(timezone.utc)
