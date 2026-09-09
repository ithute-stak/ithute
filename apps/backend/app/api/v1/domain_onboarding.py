from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.models.domains import Domain, DomainDnsMode, DomainVerificationMethod
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
    has_existing_external_dns = bool(
        wants_platform
        and discovery["lookup_status"] == "found"
        and discovery["current_nameservers"]
        and not discovery["already_on_platform_nameservers"]
    )
    verification_method = (
        DomainVerificationMethod.txt
        if payload.dns_mode == DomainDnsMode.external or has_existing_external_dns or not platform_ready
        else DomainVerificationMethod.nameserver
    )
    change_required = bool(
        wants_platform
        and platform_ready
        and not discovery["already_on_platform_nameservers"]
    )

    if wants_platform:
        ns1 = settings.nameserver_1.strip().rstrip(".")
        ns2 = settings.nameserver_2.strip().rstrip(".")
        if not platform_ready:
            next_step = (
                "Keep the current registrar nameservers unchanged. Mailbox DNS production nameserver hostnames are not configured yet, "
                "so TXT ownership verification is required until real public platform nameservers are configured."
            )
        elif has_existing_external_dns:
            next_step = (
                "Existing DNS was detected. Add the domain, prepare the staged PowerDNS zone, and add/import all existing records first. "
                "Because this is a DNS migration, publish the one-time TXT ownership record at the current DNS provider and verify it before cutover. "
                f"When the staged zone is ready, change the registrar nameservers to {ns1} and {ns2}."
            )
        elif discovery["already_on_platform_nameservers"]:
            next_step = (
                f"The domain is already delegated to {ns1} and {ns2}. Ensure the staged PowerDNS zone contains the required records, then click Verify. "
                "No TXT record is required."
            )
        else:
            next_step = (
                "No existing authoritative DNS was detected, so this is treated as a new registrar/reseller domain. "
                f"Prepare the staged PowerDNS zone and records first, then set the registrar nameservers to {ns1} and {ns2}, wait for propagation, and click Verify. "
                "No TXT record is required."
            )
    else:
        next_step = (
            "Keep the current external nameservers. TXT ownership verification is required because another DNS provider remains authoritative. "
            "Publish the ownership TXT and any later MX/SPF/DKIM/DMARC records at that provider."
        )

    return {
        "ascii_name": ascii_name,
        "unicode_name": unicode_name,
        "claim_status": claim_status,
        "requested_dns_mode": payload.dns_mode.value,
        **discovery,
        "nameserver_change_required": change_required,
        "verification_method": verification_method.value,
        "txt_required": verification_method == DomainVerificationMethod.txt,
        "has_existing_external_dns": has_existing_external_dns,
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
