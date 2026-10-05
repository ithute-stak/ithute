from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deliverability import DkimKey
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.services.deliverability import dns_readiness, infrastructure_readiness, recommended_records
from app.services.dns_phase5 import delegation_diagnostics
from app.services.engine_router import execute_dns


def _resolve(name: str, rtype: str) -> list[str]:
    execution = execute_dns(
        [{"id": "health", "name": name, "type": rtype, "timeout_ms": 5000}],
        concurrency=1,
    )
    results = execution.value.get("results", []) if isinstance(execution.value, dict) else []
    if not results or not isinstance(results[0], dict):
        return []
    return [
        str(value).strip().rstrip(".").lower()
        for value in (results[0].get("values") or [])
        if str(value).strip()
    ]


def _host_addresses(hostname: str) -> set[str]:
    return set(_resolve(hostname, "A") + _resolve(hostname, "AAAA"))


def _discovery_check(domain: str, label: str) -> dict:
    host = f"{label}.{domain}".rstrip(".").lower()
    expected = settings.mail_hostname.rstrip(".").lower()
    aliases = _resolve(host, "CNAME")
    expected_addresses = _host_addresses(expected)
    observed_addresses = _host_addresses(host)
    healthy = expected in aliases or bool(expected_addresses and expected_addresses.intersection(observed_addresses))
    return {
        "id": label,
        "label": "Autoconfig" if label == "autoconfig" else "Autodiscover",
        "status": "healthy" if healthy else "attention",
        "required": False,
        "detail": (
            f"{host} resolves to the Ithute mail service."
            if healthy
            else f"Optional: point {host} to {expected} to simplify mail-client setup."
        ),
        "observed": {"cname": aliases, "addresses": sorted(observed_addresses)},
        "expected": expected,
    }


def _active_dkim(db: Session, domain_id: UUID) -> DkimKey | None:
    return db.scalar(
        select(DkimKey)
        .where(DkimKey.domain_id == domain_id, DkimKey.active.is_(True))
        .order_by(DkimKey.created_at.desc())
    )


def _check(check_id: str, label: str, healthy: bool, detail: str, *, required: bool = True, observed=None, expected=None) -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": "healthy" if healthy else "attention",
        "required": required,
        "detail": detail,
        "observed": observed,
        "expected": expected,
    }


def domain_mail_health(db: Session, domain: Domain) -> dict:
    domain_name = domain.ascii_name.rstrip(".").lower()
    checks: list[dict] = []

    ownership_ok = domain.status == DomainStatus.verified and domain.ownership_verified_at is not None
    checks.append(
        _check(
            "ownership",
            "Domain ownership",
            ownership_ok,
            "Domain ownership is verified." if ownership_ok else "Verify domain ownership before treating mail DNS as production-ready.",
        )
    )

    if domain.dns_mode == DomainDnsMode.platform:
        delegation = delegation_diagnostics(domain_name)
        checks.append(
            _check(
                "delegation",
                "Nameserver delegation",
                bool(delegation.get("ready")),
                "Public delegation matches Ithute authoritative DNS." if delegation.get("ready") else "Registrar delegation does not fully match the Ithute nameservers yet.",
                observed=delegation.get("observed_nameservers") or [],
                expected=delegation.get("expected_nameservers") or [],
            )
        )
    else:
        checks.append(
            {
                "id": "delegation",
                "label": "DNS hosting",
                "status": "healthy",
                "required": False,
                "detail": "This domain intentionally keeps DNS with an external provider.",
                "observed": "external",
                "expected": "external",
            }
        )

    key = _active_dkim(db, domain.id)
    expected_records: list[dict] = []
    if key is not None:
        readiness = dns_readiness(
            domain_name,
            settings.mail_hostname,
            key.selector,
            key.public_key_b64,
            mta_sts_id=settings.mail_mta_sts_policy_id if settings.mail_mta_sts_enabled else None,
            mta_sts_ip=settings.bootstrap_public_ip if settings.mail_mta_sts_enabled else None,
            tls_report_address=settings.mail_tls_reporting_address or None,
        )
        expected_records = readiness["recommended_records"]
        labels = {
            "mx": ("MX routing", "MX points to the Ithute mail gateway.", "MX does not point to the Ithute mail gateway."),
            "spf": ("SPF", "SPF authorizes the Ithute mail route.", "SPF is missing or does not match the Ithute policy."),
            "dkim": ("DKIM", f"DKIM selector {key.selector} is published and matches the active signing key.", f"DKIM selector {key.selector} is missing or does not match the active signing key."),
            "dmarc": ("DMARC", "DMARC is published for the domain.", "DMARC is missing or invalid."),
            "mta_sts": ("MTA-STS policy ID", "MTA-STS DNS policy identity is published.", "MTA-STS DNS policy identity is missing or stale."),
            "mta_sts_host": ("MTA-STS HTTPS host", "MTA-STS hostname resolves to the Ithute edge.", "MTA-STS hostname does not resolve to the Ithute edge."),
            "tls_rpt": ("TLS reporting", "TLS-RPT reporting is published.", "TLS-RPT reporting is missing or does not match Ithute policy."),
        }
        required_items = ["mx", "spf", "dkim", "dmarc"]
        if settings.mail_mta_sts_enabled:
            required_items.extend(["mta_sts", "mta_sts_host"])
        if settings.mail_tls_reporting_address:
            required_items.append("tls_rpt")
        for item in required_items:
            label, good, bad = labels[item]
            checks.append(_check(item, label, bool(readiness["checks"].get(item)), good if readiness["checks"].get(item) else bad))
    else:
        expected_records = [
            {
                "name": domain_name,
                "type": "MX",
                "value": f"10 {settings.mail_hostname.rstrip('.')}.",
                "purpose": "mail-routing",
            },
            {"name": domain_name, "type": "TXT", "value": "v=spf1 mx -all", "purpose": "spf"},
            {"name": f"_dmarc.{domain_name}", "type": "TXT", "value": "v=DMARC1; p=quarantine; adkim=s; aspf=s; pct=100", "purpose": "dmarc"},
        ]
        pending_checks = [("mx", "MX routing"), ("spf", "SPF"), ("dkim", "DKIM"), ("dmarc", "DMARC")]
        if settings.mail_mta_sts_enabled:
            expected_records.extend([
                {"name": f"_mta-sts.{domain_name}", "type": "TXT", "value": f"v=STSv1; id={settings.mail_mta_sts_policy_id}", "purpose": "mta-sts"},
                {"name": f"mta-sts.{domain_name}", "type": "A", "value": settings.bootstrap_public_ip or "<Ithute edge IP>", "purpose": "mta-sts-host"},
            ])
            pending_checks.extend([("mta_sts", "MTA-STS policy ID"), ("mta_sts_host", "MTA-STS HTTPS host")])
        if settings.mail_tls_reporting_address:
            expected_records.append({
                "name": f"_smtp._tls.{domain_name}",
                "type": "TXT",
                "value": f"v=TLSRPTv1; rua=mailto:{settings.mail_tls_reporting_address}",
                "purpose": "tls-rpt",
            })
            pending_checks.append(("tls_rpt", "TLS reporting"))
        for item, label in pending_checks:
            checks.append(
                {
                    "id": item,
                    "label": label,
                    "status": "pending",
                    "required": True,
                    "detail": "Reconcile mail DNS to create the active DKIM identity and publish the production mail records.",
                    "observed": None,
                    "expected": None,
                }
            )

    infra = infrastructure_readiness(settings.mail_hostname, settings.mail_public_ip)
    checks.append(
        _check(
            "mail-host",
            "Mail host forward DNS",
            bool(infra["checks"].get("forward_dns")),
            "Mail hostname resolves to the configured public mail IP." if infra["checks"].get("forward_dns") else "Mail hostname forward DNS does not resolve to the configured public mail IP.",
            observed=infra.get("addresses") or [],
            expected=infra.get("public_ip"),
        )
    )
    checks.append(
        _check(
            "ptr",
            "PTR / reverse DNS",
            bool(infra["checks"].get("fcrdns")),
            "Forward-confirmed reverse DNS is healthy." if infra["checks"].get("fcrdns") else "PTR/forward-confirmed reverse DNS needs attention for deliverability.",
            observed=infra.get("ptr_hosts") or [],
            expected=infra.get("mail_hostname"),
        )
    )

    checks.append(_discovery_check(domain_name, "autoconfig"))
    checks.append(_discovery_check(domain_name, "autodiscover"))

    required = [item for item in checks if item.get("required")]
    healthy_required = sum(1 for item in required if item["status"] == "healthy")
    pending_required = sum(1 for item in required if item["status"] == "pending")
    score = round((healthy_required / len(required)) * 100) if required else 100
    if required and healthy_required == len(required):
        overall = "healthy"
    elif pending_required and healthy_required == 0:
        overall = "pending"
    else:
        overall = "attention"

    return {
        "domain": domain_name,
        "mail_enabled": domain.mail_enabled,
        "dns_mode": domain.dns_mode.value,
        "overall_status": overall,
        "score": score,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "required": len(required),
            "healthy": healthy_required,
            "attention": sum(1 for item in required if item["status"] == "attention"),
            "pending": pending_required,
            "optional_attention": sum(1 for item in checks if not item.get("required") and item["status"] != "healthy"),
        },
        "checks": checks,
        "expected_records": expected_records,
        "mail_hostname": settings.mail_hostname.rstrip("."),
        "mail_public_ip": settings.mail_public_ip,
        "dkim_selector": key.selector if key else None,
    }
