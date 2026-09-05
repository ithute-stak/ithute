from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.models.domains import Domain, DomainDnsMode
from app.services.billing import billing_summary, entitlement_decision
from app.services.domain_discovery import inspect_nameservers
from app.services.domains import normalize_domain

router = APIRouter(tags=["domain-onboarding"])


class DomainInspectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=320)
    dns_mode: DomainDnsMode = DomainDnsMode.platform


@router.post("/tenants/{tenant_id}/domain-onboarding/inspect")
def inspect_domain_onboarding(
    tenant_id: UUID,
    payload: DomainInspectionRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    try:
        ascii_name, unicode_name = normalize_domain(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = db.scalar(select(Domain).where(Domain.ascii_name == ascii_name))
    claim_status = "available"
    if existing is not None:
        claim_status = "this_organization" if existing.tenant_id == tenant_id else "another_organization"

    platform_nameservers = [settings.nameserver_1, settings.nameserver_2]
    discovery = inspect_nameservers(ascii_name, platform_nameservers)
    billing = billing_summary(db, tenant_id)
    entitlement = entitlement_decision(db, tenant_id, "domain")

    usage = entitlement.get("usage") or {}
    limits = entitlement.get("limits") or {}
    used_domains = int(usage.get("domains", 0))
    domain_limit = limits.get("domains")
    remaining = max(0, int(domain_limit) - used_domains) if domain_limit is not None else None

    wants_platform = payload.dns_mode == DomainDnsMode.platform
    platform_ready = bool(discovery["platform_nameservers_configured"])
    change_required = bool(
        wants_platform
        and platform_ready
        and not discovery["already_on_platform_nameservers"]
    )
    if wants_platform:
        if not platform_ready:
            next_step = (
                "Keep the current registrar nameservers unchanged. Mailbox DNS production nameserver hostnames are not configured yet, "
                "so it is unsafe to delegate the domain to this platform. Complete TXT ownership verification now; configure real public "
                "Mailbox DNS nameservers and their required glue/A records before any registrar nameserver change."
            )
        elif discovery["lookup_status"] == "found" and change_required:
            next_step = (
                "Keep the current nameservers in place while TXT ownership verification is completed. "
                "After verification and PowerDNS zone preparation, replace the registrar nameservers with the Mailbox DNS nameservers."
            )
        elif discovery["already_on_platform_nameservers"]:
            next_step = "The domain is already delegated to Mailbox DNS nameservers; continue with ownership verification and zone reconciliation."
        else:
            next_step = "Complete ownership verification first. Re-run nameserver discovery before changing registrar delegation."
    else:
        next_step = (
            "Keep the current external nameservers. Publish the ownership TXT and any later MX/SPF/DKIM/DMARC records at that DNS provider; "
            "Mailbox DNS will host email services without becoming authoritative for the zone."
        )

    return {
        "ascii_name": ascii_name,
        "unicode_name": unicode_name,
        "claim_status": claim_status,
        "requested_dns_mode": payload.dns_mode.value,
        **discovery,
        "nameserver_change_required": change_required,
        "next_step": next_step,
        "package": billing.get("subscription"),
        "package_usage": billing.get("usage") or usage,
        "domain_capacity": {
            "allowed": bool(entitlement.get("allowed")),
            "reason": entitlement.get("reason"),
            "used": used_domains,
            "limit": domain_limit,
            "remaining": remaining,
        },
    }
