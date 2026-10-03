from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Domain, MailNode
from app.models.domains import DomainStatus
from app.models.mail import Mailbox, MailboxStatus, MailboxStorageType
from app.services.mail_transport_security import mta_sts_policy
from app.services.mail_client_settings import (
    autodiscover_email_address,
    outlook_autodiscover,
    thunderbird_autoconfig,
)

router = APIRouter(tags=["mail-discovery"])
_XML_MEDIA_TYPE = "application/xml; charset=utf-8"


def _hostname_for_address(db: Session, address: str) -> str | None:
    mailbox = db.scalar(
        select(Mailbox).where(
            Mailbox.address == address.lower(),
            Mailbox.status == MailboxStatus.active,
        )
    )
    if mailbox is None or mailbox.storage_type != MailboxStorageType.external or mailbox.mail_node_id is None:
        return None
    node = db.scalar(
        select(MailNode).where(
            MailNode.id == mailbox.mail_node_id,
            MailNode.status == "active",
            (MailNode.tenant_id.is_(None)) | (MailNode.tenant_id == mailbox.tenant_id),
        )
    )
    return node.hostname if node is not None else None


def _xml_response(content: bytes) -> Response:
    return Response(
        content=content,
        media_type=_XML_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


def _thunderbird_response(emailaddress: str, db: Session) -> Response:
    try:
        return _xml_response(thunderbird_autoconfig(emailaddress, _hostname_for_address(db, emailaddress)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mail/config-v1.1.xml", include_in_schema=False)
def thunderbird_mail_config(
    emailaddress: str = Query(..., min_length=3, max_length=254),
    db: Session = Depends(get_db),
):
    return _thunderbird_response(emailaddress, db)


@router.get("/.well-known/autoconfig/mail/config-v1.1.xml", include_in_schema=False)
def thunderbird_well_known_config(
    emailaddress: str = Query(..., min_length=3, max_length=254),
    db: Session = Depends(get_db),
):
    return _thunderbird_response(emailaddress, db)


@router.post("/autodiscover/autodiscover.xml", include_in_schema=False)
async def microsoft_autodiscover(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    if len(payload) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Autodiscover request is too large")
    try:
        email = autodiscover_email_address(payload)
        return _xml_response(outlook_autodiscover(email, _hostname_for_address(db, email)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.get("/.well-known/mta-sts.txt", include_in_schema=False)
def mta_sts_policy_document(request: Request, db: Session = Depends(get_db)):
    host = request.headers.get("host", "").split(":", 1)[0].strip().lower().rstrip(".")
    if not host.startswith("mta-sts."):
        raise HTTPException(status_code=404, detail="MTA-STS policy host not found")
    domain_name = host[len("mta-sts.") :]
    domain = db.scalar(
        select(Domain).where(
            Domain.ascii_name == domain_name,
            Domain.status == DomainStatus.verified,
            Domain.mail_enabled.is_(True),
        )
    )
    if domain is None:
        raise HTTPException(status_code=404, detail="MTA-STS policy not found")
    return PlainTextResponse(
        content=mta_sts_policy(domain.ascii_name),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
