"""Read-only DNSSEC monitor runner; scheduling belongs to deployment.

Each managed domain is checked and recorded independently. A database advisory
lock prevents overlapping full scans; per-domain row locks serialize writes.
"""
from __future__ import annotations

import logging
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.services.dns_phase5 import delegation_diagnostics
from app.services.powerdns import PowerDNSClient
from app.services.registrar_dnssec import DSRecord
from app.services.dnssec_resolver_validation import validating_resolver_check
from app.services.dnssec_incidents import classify_dnssec_observation
from app.services.dnssec_monitor_persistence import record_dnssec_observation

logger = logging.getLogger(__name__)
_LOCK_KEY = 912003407


def build_dnssec_monitor_readiness(zone: dict, keys: list[dict], info: dict) -> dict:
    candidates = [ds for key in keys for ds in (key.get("ds") or [])]
    expected = []
    for value in candidates:
        try:
            expected.append(DSRecord.parse(value))
        except (TypeError, ValueError):
            continue
    observed = []
    for value in info.get("parent_ds") or []:
        try:
            observed.append(DSRecord.parse(value))
        except (TypeError, ValueError):
            continue
    parent_error = info.get("parent_ds_error")
    lookup_failed = bool(parent_error and parent_error not in {"NoAnswer", "NXDOMAIN"} and not observed)
    parent_matched = any(record in observed for record in expected)
    readiness = {"steps": [
        {"key": "delegation", "state": "complete" if info.get("ready") else "blocked" if info.get("delegation_error") else "pending"},
        {"key": "signing", "state": "complete" if zone.get("dnssec") else "pending"},
        {"key": "parent", "state": "blocked" if lookup_failed else "complete" if parent_matched else "pending"},
    ]}
    return readiness


def run_dnssec_monitor(db: Session, *, limit: int = 100) -> dict:
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    acquired = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _LOCK_KEY}
    ).scalar()
    if not acquired:
        db.rollback()
        return {"checked": 0, "failed": 0, "skipped": "already_running"}

    domains = db.scalars(
        select(Domain).where(
            Domain.dns_mode == DomainDnsMode.platform,
            Domain.status != DomainStatus.archived,
        ).order_by(Domain.id).limit(limit)
    ).all()
    checked = 0
    failures = 0
    for domain in domains:
        try:
            info = delegation_diagnostics(domain.ascii_name)
            resolver = validating_resolver_check(domain.ascii_name)
            # Read the authoritative zone and KSKs before classifying health.
            # Never use a resolver AD flag to override missing local evidence.
            pdns = PowerDNSClient()
            zone = pdns.get_zone(domain.ascii_name)
            keys = pdns.list_cryptokeys(domain.ascii_name)
            readiness = build_dnssec_monitor_readiness(zone, keys, info)
            observation = classify_dnssec_observation(readiness, resolver)
            with db.begin_nested():
                record_dnssec_observation(
                    db, tenant_id=domain.tenant_id, domain_id=domain.id,
                    observation=observation,
                )
            checked += 1
        except Exception:
            failures += 1
            logger.exception("DNSSEC monitoring failed for domain %s", domain.id)
    # Hold the transaction-scoped advisory lock through the entire scan.
    db.commit()
    return {"checked": checked, "failed": failures, "scanned": len(domains)}
