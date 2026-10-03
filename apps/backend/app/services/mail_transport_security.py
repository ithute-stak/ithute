from __future__ import annotations

import hashlib

from app.core.config import settings


def policy_hostname(domain: str) -> str:
    return f"mta-sts.{domain.rstrip('.').lower()}"


def mta_sts_policy(domain: str) -> str:
    domain = domain.rstrip(".").lower()
    mail_host = settings.mail_hostname.rstrip(".").lower()
    return (
        "version: STSv1\n"
        f"mode: {settings.mail_mta_sts_mode}\n"
        f"mx: {mail_host}\n"
        f"max_age: {settings.mail_mta_sts_max_age_seconds}\n"
    )


def mta_sts_policy_id(domain: str) -> str:
    material = (
        f"{domain.rstrip('.').lower()}|{settings.mail_hostname.rstrip('.').lower()}|"
        f"{settings.mail_mta_sts_mode}|{settings.mail_mta_sts_max_age_seconds}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def transport_security_records(domain: str) -> list[dict]:
    domain = domain.rstrip(".").lower()
    records: list[dict] = []
    if settings.mail_mta_sts_enabled and settings.bootstrap_public_ip:
        records.append(
            {
                "name": policy_hostname(domain),
                "type": "A",
                "value": settings.bootstrap_public_ip,
                "purpose": "mta-sts-host",
            }
        )
        records.append(
            {
                "name": f"_mta-sts.{domain}",
                "type": "TXT",
                "value": f"v=STSv1; id={mta_sts_policy_id(domain)}",
                "purpose": "mta-sts",
            }
        )
    if settings.mail_tls_report_address:
        records.append(
            {
                "name": f"_smtp._tls.{domain}",
                "type": "TXT",
                "value": f"v=TLSRPTv1; rua=mailto:{settings.mail_tls_report_address}",
                "purpose": "tls-rpt",
            }
        )
    return records
