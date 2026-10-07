from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DkimKey, Domain, DomainStatus, MailRelationship, Mailbox


@dataclass(frozen=True)
class FirstContactPlan:
    first_contact_recipients: tuple[str, ...]
    established_recipients: tuple[str, ...]
    visible_badge: bool
    sender_domain_verified: bool
    dkim_configured: bool

    @property
    def sender_identity_authenticated(self) -> bool:
        return self.sender_domain_verified and self.dkim_configured

    def public_dict(self) -> dict:
        return {
            "protocol": "ithute-verified-first-contact-v1",
            "relationship": "new" if self.first_contact_recipients else "established",
            "first_contact_count": len(self.first_contact_recipients),
            "established_count": len(self.established_recipients),
            "visible_badge": self.visible_badge,
            "sender_domain_authenticated": self.sender_identity_authenticated,
            "checks": {
                "domain_ownership_verified": self.sender_domain_verified,
                "dkim_configured": self.dkim_configured,
                "tls_required": True,
            },
            "claims_message_safe": False,
            "separate_advert_sent": False,
        }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))


def prepare_first_contact(
    db: Session,
    *,
    sender_address: str,
    visible_recipients: list[str],
    hidden_recipients: list[str] | None = None,
) -> tuple[Mailbox, FirstContactPlan]:
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == sender_address.lower()))
    if mailbox is None:
        raise ValueError("Sender mailbox is not managed by Ithute")

    visible = _unique(visible_recipients)
    all_recipients = _unique([*visible, *(hidden_recipients or [])])
    existing = {
        row.peer_address: row
        for row in db.scalars(
            select(MailRelationship).where(
                MailRelationship.mailbox_id == mailbox.id,
                MailRelationship.peer_address.in_(all_recipients),
            )
        ).all()
    }
    first = tuple(address for address in all_recipients if address not in existing)
    established = tuple(address for address in all_recipients if address in existing)

    domain = db.get(Domain, mailbox.domain_id)
    domain_verified = bool(domain and domain.status == DomainStatus.verified and domain.ownership_verified_at)
    dkim_configured = bool(
        db.scalar(
            select(DkimKey.id).where(
                DkimKey.tenant_id == mailbox.tenant_id,
                DkimKey.domain_id == mailbox.domain_id,
                DkimKey.active.is_(True),
            ).limit(1)
        )
    )
    visible_badge = bool(visible) and all(address in first for address in visible)
    return mailbox, FirstContactPlan(
        first_contact_recipients=first,
        established_recipients=established,
        visible_badge=visible_badge,
        sender_domain_verified=domain_verified,
        dkim_configured=dkim_configured,
    )


def decorate_first_contact_text(body: str, plan: FirstContactPlan) -> str:
    if not plan.visible_badge:
        return body
    identity = "Sender domain authenticated by Ithute." if plan.sender_identity_authenticated else "Sender identity is managed by Ithute Mail."
    footer = (
        "Ithute Verified First Contact\n"
        f"{identity}\n"
        "TLS-protected transport is required by Ithute.\n"
        "Authentication does not guarantee that message content is safe.\n"
        "Powered by Ithute"
    )
    return f"{body.rstrip()}\n\n---\n{footer}" if body.strip() else footer


def decorate_first_contact_html(body: str, plan: FirstContactPlan) -> str:
    if not plan.visible_badge:
        return body
    identity = "Sender domain authenticated by Ithute." if plan.sender_identity_authenticated else "Sender identity is managed by Ithute Mail."
    badge = (
        '<div data-ithute-first-contact="v1" style="margin-top:24px;padding:14px;border:1px solid #d1d5db;'
        'border-radius:10px;font-family:Arial,sans-serif;font-size:13px;line-height:1.45">'
        '<strong>Ithute Verified First Contact</strong><br>'
        f'{html.escape(identity)}<br>'
        'TLS-protected transport is required by Ithute.<br>'
        '<small>Authentication does not guarantee that message content is safe. Powered by Ithute.</small>'
        '</div>'
    )
    return (body or "") + badge


def record_successful_send(
    db: Session,
    *,
    mailbox: Mailbox,
    recipients: list[str],
) -> None:
    now = datetime.now(timezone.utc)
    for peer in _unique(recipients):
        row = db.scalar(
            select(MailRelationship).where(
                MailRelationship.mailbox_id == mailbox.id,
                MailRelationship.peer_address == peer,
            )
        )
        if row is None:
            row = MailRelationship(
                tenant_id=mailbox.tenant_id,
                mailbox_id=mailbox.id,
                peer_address=peer,
                state="new",
                first_contact_at=now,
                last_sent_at=now,
                messages_sent=1,
            )
            db.add(row)
        else:
            row.messages_sent += 1
            row.last_sent_at = now
            if row.replies_received > 0 or row.messages_sent >= 2:
                row.state = "established"
    db.commit()
