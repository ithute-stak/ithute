from __future__ import annotations

from dataclasses import dataclass
import socket

import dns.exception
import dns.resolver

from app.core.config import settings


@dataclass(frozen=True)
class DnsTemplate:
    name: str
    label: str
    description: str
    records: list[dict]


def dns_templates(domain: str) -> list[DnsTemplate]:
    domain = domain.rstrip(".")
    return [
        DnsTemplate(
            name="website",
            label="Website starter",
            description="Apex and www records for a typical website.",
            records=[
                {"name": "@", "type": "A", "ttl": 3600, "contents": ["192.0.2.10"]},
                {"name": "www", "type": "CNAME", "ttl": 3600, "contents": [f"{domain}."]},
            ],
        ),
        DnsTemplate(
            name="mail-readiness",
            label="Mail readiness",
            description="Starter records for future Mailbox DNS mail hosting. Replace the example mail host/IP before applying in production.",
            records=[
                {"name": "mail", "type": "A", "ttl": 3600, "contents": ["192.0.2.25"]},
                {"name": "@", "type": "MX", "ttl": 3600, "contents": [f"10 mail.{domain}."]},
                {"name": "@", "type": "TXT", "ttl": 3600, "contents": ["\"v=spf1 -all\""]},
                {"name": "_dmarc", "type": "TXT", "ttl": 3600, "contents": ["\"v=DMARC1; p=none; rua=mailto:dmarc@" + domain + "\""]},
            ],
        ),
        DnsTemplate(
            name="security-baseline",
            label="DNS security baseline",
            description="CAA policy restricting certificate issuance to Let's Encrypt.",
            records=[
                {"name": "@", "type": "CAA", "ttl": 3600, "contents": ["0 issue \"letsencrypt.org\""]},
            ],
        ),
    ]


def _resolve(name: str, rtype: str) -> tuple[list[str], str | None]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.lifetime = 5
    try:
        answers = resolver.resolve(name, rtype)
        values = [answer.to_text().rstrip(".") for answer in answers]
        return values, None
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
        return [], exc.__class__.__name__
    except (dns.resolver.NoNameservers, dns.exception.Timeout, OSError) as exc:
        return [], str(exc)[:240]


def delegation_diagnostics(domain: str) -> dict:
    domain = domain.rstrip(".").lower()
    expected = [settings.nameserver_1.rstrip(".").lower(), settings.nameserver_2.rstrip(".").lower()]
    observed_ns, ns_error = _resolve(domain, "NS")
    observed_normalized = sorted(value.lower() for value in observed_ns)
    expected_normalized = sorted(expected)

    nameserver_addresses: dict[str, dict] = {}
    for ns in expected:
        a, a_error = _resolve(ns, "A")
        aaaa, aaaa_error = _resolve(ns, "AAAA")
        nameserver_addresses[ns] = {
            "a": a,
            "aaaa": aaaa,
            "resolves": bool(a or aaaa),
            "errors": [error for error in (a_error, aaaa_error) if error],
        }

    soa, soa_error = _resolve(domain, "SOA")
    ds, ds_error = _resolve(domain, "DS")
    delegation_matches = all(ns in observed_normalized for ns in expected_normalized)
    return {
        "domain": domain,
        "expected_nameservers": expected,
        "observed_nameservers": observed_ns,
        "delegation_matches": delegation_matches,
        "delegation_error": ns_error,
        "soa": soa,
        "soa_error": soa_error,
        "parent_ds": ds,
        "parent_ds_present": bool(ds),
        "parent_ds_error": ds_error,
        "nameserver_addresses": nameserver_addresses,
        "ready": delegation_matches and all(item["resolves"] for item in nameserver_addresses.values()),
    }
