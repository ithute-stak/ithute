from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import finance_role_for_user, get_current_user, require_actual_platform_owner, require_platform_owner
from app.core.config import settings
from app.db.session import get_db
from app.models import FinanceClient, FinanceDeliveryEvent, FinanceInvoice, FinancePortalAccess, FinanceRoleGrant, User
from app.services.finance_invoice_multi import render_invoice_pdf
from app.services.finance_ledger import invoice_financial_out
from app.services.finance_mail import send_finance_message
from app.services.finance_statements import client_payment_behaviour, render_statement_pdf

router = APIRouter(prefix="/finance/completion", tags=["finance-completion"])
portal_router = APIRouter(prefix="/finance/portal", tags=["finance-portal"])

ROLE_RANK = {"viewer": 1, "clerk": 2, "approver": 3, "admin": 4}


class RoleGrantIn(BaseModel):
    user_id: UUID
    role: str = Field(pattern="^(viewer|clerk|approver|admin)$")
    active: bool = True


class PortalLinkIn(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=720)
    send_email: bool = True


class DeliveryEventIn(BaseModel):
    invoice_id: UUID
    event_type: str = Field(pattern="^(accepted|delivered|deferred|bounced|failed)$")
    source: str = Field(default="manual_or_provider", min_length=2, max_length=80)
    provider_message_id: str = Field(default="", max_length=320)
    detail: str = Field(default="", max_length=4000)
    occurred_at: datetime | None = None


def _grant_out(row: FinanceRoleGrant, user: User | None = None) -> dict:
    return {
        "id": str(row.id), "user_id": str(row.user_id), "email": user.email if user else None,
        "full_name": user.full_name if user else None, "role": row.role, "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_out(row: FinanceDeliveryEvent) -> dict:
    return {
        "id": str(row.id), "invoice_id": str(row.invoice_id), "event_type": row.event_type,
        "source": row.source, "provider_message_id": row.provider_message_id, "detail": row.detail,
        "occurred_at": row.occurred_at.isoformat(), "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _portal_access(db: Session, raw_token: str | None) -> tuple[FinancePortalAccess, FinanceClient]:
    if not raw_token:
        raise HTTPException(status_code=401, detail="Client portal token required")
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = db.scalar(select(FinancePortalAccess).where(FinancePortalAccess.token_hash == token_hash))
    now = datetime.now(timezone.utc)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Client portal link is invalid or expired")
    client = db.get(FinanceClient, row.client_id)
    if client is None or not client.active:
        raise HTTPException(status_code=404, detail="Finance client not found")
    row.last_used_at = now
    db.commit()
    return row, client


def _client_invoices(db: Session, client_id: UUID) -> list[FinanceInvoice]:
    return list(db.scalars(
        select(FinanceInvoice)
        .options(selectinload(FinanceInvoice.payments), selectinload(FinanceInvoice.credit_notes), selectinload(FinanceInvoice.items))
        .where(FinanceInvoice.client_id == client_id)
        .order_by(FinanceInvoice.created_at.desc())
    ).all())


@router.get("/access")
def finance_access(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    role = "owner" if current.is_platform_owner else finance_role_for_user(db, current.id)
    return {"allowed": bool(role), "role": role, "is_platform_owner": current.is_platform_owner}


@router.get("/roles")
def list_role_grants(db: Session = Depends(get_db), current: User = Depends(require_actual_platform_owner)):
    del current
    rows = list(db.scalars(select(FinanceRoleGrant).order_by(FinanceRoleGrant.created_at.asc())).all())
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([r.user_id for r in rows] or [UUID(int=0)]))).all()}
    return {"items": [_grant_out(row, users.get(row.user_id)) for row in rows]}


@router.get("/eligible-users")
def eligible_users(db: Session = Depends(get_db), current: User = Depends(require_actual_platform_owner)):
    del current
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.email.asc())).all()
    return {"items": [{"id": str(user.id), "email": user.email, "full_name": user.full_name, "is_platform_owner": user.is_platform_owner} for user in users]}


@router.put("/roles")
def upsert_role(payload: RoleGrantIn, db: Session = Depends(get_db), current: User = Depends(require_actual_platform_owner)):
    user = db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Active user not found")
    if user.is_platform_owner:
        raise HTTPException(status_code=409, detail="Platform owner already has full Finance access")
    row = db.scalar(select(FinanceRoleGrant).where(FinanceRoleGrant.user_id == user.id))
    if row is None:
        row = FinanceRoleGrant(user_id=user.id, role=payload.role, active=payload.active, granted_by_user_id=current.id)
        db.add(row)
    else:
        row.role = payload.role; row.active = payload.active; row.granted_by_user_id = current.id
    db.commit(); db.refresh(row)
    return _grant_out(row, user)


@router.delete("/roles/{grant_id}", status_code=204)
def delete_role(grant_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_actual_platform_owner)):
    del current
    row = db.get(FinanceRoleGrant, grant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finance role grant not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@router.post("/portal-links/{client_id}")
def create_portal_link(client_id: UUID, payload: PortalLinkIn, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    raw = secrets.token_urlsafe(48)
    row = FinancePortalAccess(
        client_id=client.id, token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=payload.expires_hours), created_by_user_id=current.id,
    )
    db.add(row); db.commit(); db.refresh(row)
    frontend = settings.frontend_url.rstrip("/")
    link = f"{frontend}/finance-portal#token={raw}"
    if payload.send_email:
        body = (
            f"Dear {client.name},\n\nUse the secure link below to view your Ithute invoices, outstanding balance and statement of account.\n\n"
            f"{link}\n\nThis link expires in {payload.expires_hours} hours.\n\nRegards,\nIthute Finance"
        )
        try:
            send_finance_message(db, recipient=client.email, subject="Your secure Ithute Finance portal", text_body=body, html_body=None, attachment_filename=None, attachment_data=None)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Portal link was created but email delivery failed: {str(exc)[:300]}") from exc
    return {"client_id": str(client.id), "recipient": client.email, "expires_at": row.expires_at.isoformat(), "portal_url": link, "emailed": payload.send_email}


@router.get("/delivery-events/{invoice_id}")
def list_delivery_events(invoice_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    rows = db.scalars(select(FinanceDeliveryEvent).where(FinanceDeliveryEvent.invoice_id == invoice_id).order_by(FinanceDeliveryEvent.occurred_at.asc())).all()
    return {"items": [_event_out(row) for row in rows]}


@router.post("/delivery-events", status_code=201)
def record_delivery_event(payload: DeliveryEventIn, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    invoice = db.get(FinanceInvoice, payload.invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    row = FinanceDeliveryEvent(
        invoice_id=invoice.id, event_type=payload.event_type, source=payload.source.strip(),
        provider_message_id=payload.provider_message_id.strip(), detail=payload.detail.strip(),
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
    )
    db.add(row); db.commit(); db.refresh(row)
    return _event_out(row)


@portal_router.get("/me")
def portal_me(x_finance_portal_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _, client = _portal_access(db, x_finance_portal_token)
    invoices = _client_invoices(db, client.id)
    rows = [invoice_financial_out(row) for row in invoices if row.status != "cancelled"]
    behaviour = client_payment_behaviour(client, invoices)
    return {
        "client": {"id": str(client.id), "name": client.name, "email": client.email, "address": client.address, "phone": client.phone},
        "summary": behaviour,
        "invoices": rows,
    }


@portal_router.get("/invoices/{invoice_id}/pdf")
def portal_invoice_pdf(invoice_id: UUID, x_finance_portal_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _, client = _portal_access(db, x_finance_portal_token)
    invoice = db.scalar(select(FinanceInvoice).where(FinanceInvoice.id == invoice_id, FinanceInvoice.client_id == client.id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf = render_invoice_pdf(invoice)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'})


@portal_router.get("/statement.pdf")
def portal_statement_pdf(x_finance_portal_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _, client = _portal_access(db, x_finance_portal_token)
    pdf = render_statement_pdf(client, _client_invoices(db, client.id), as_of=date.today())
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="Ithute-Statement.pdf"'})
