from __future__ import annotations

import ipaddress
import socket
import ssl
from datetime import datetime, timezone
from typing import Any

import dns.exception
import dns.resolver
import httpx
from sqlalchemy.orm import Session

from app.models import DomainIntelligenceProfile
from app.services.mail_reputation import refresh_domain_profile

RDAP_BASE_URL = "https://rdap.org/domain/"
PUBLIC_SUFFIX_HINTS = {"co.ls", "org.ls", "gov.ls", "ac.ls", "net.ls"}


def _safe_domain(value: str) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain or len(domain) > 253 or "@" in domain or "://" in domain:
        raise ValueError("invalid domain")
    labels = domain.split(".")
    if len(labels) < 2:
        raise ValueError("domain must contain a public suffix")
    for label in labels:
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(ch.isalnum() or ch == "-" for ch in label)
        ):
            raise ValueError("invalid domain")
    return domain


def _public_addresses(domain: str) -> list[str]:
    addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    for info in infos:
        raw = str(info[4][0])
        try:
            parsed = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not parsed.is_global:
            continue
        if raw not in addresses:
            addresses.append(raw)
    return addresses[:8]


def _dns_values(domain: str, record_type: str) -> list[str]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 2.0
    resolver.lifetime = 4.0
    try:
        answer = resolver.resolve(domain, record_type, raise_on_no_answer=False)
    except (dns.exception.DNSException, OSError):
        return []
    if answer.rrset is None:
        return []
    values = []
    for item in answer:
        text = item.to_text().strip()
        if record_type in {"MX", "NS"}:
            text = text.rstrip(".")
        values.append(text)
    return sorted(set(values))[:20]


def _rdap_created_at(domain: str, timeout_seconds: float) -> tuple[datetime | None, dict[str, Any]]:
    url = RDAP_BASE_URL + domain
    evidence: dict[str, Any] = {"endpoint": "rdap.org", "status": "unavailable"}
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"Accept": "application/rdap+json, application/json"},
        ) as client:
            response = client.get(url)
    except httpx.HTTPError:
        return None, evidence
    evidence["http_status"] = response.status_code
    if response.status_code != 200:
        return None, evidence
    try:
        payload = response.json()
    except ValueError:
        return None, evidence
    evidence["status"] = "available"
    evidence["handle_present"] = bool(payload.get("handle"))
    evidence["entities_count"] = len(payload.get("entities") or [])
    for event in payload.get("events") or []:
        action = str(event.get("eventAction") or "").lower()
        value = str(event.get("eventDate") or "").strip()
        if action not in {"registration", "registered"} or not value:
            continue
        try:
            created = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created.astimezone(timezone.utc), evidence
    return None, evidence


def _tls_http_probe(domain: str, addresses: list[str], timeout_seconds: float) -> dict[str, Any]:
    result = {
        "tls_present": False,
        "tls_version": None,
        "certificate_matches_hostname": False,
        "https_status": None,
        "public_address_count": len(addresses),
    }
    if not addresses:
        return result

    context = ssl.create_default_context()
    for address in addresses[:2]:
        raw = None
        tls = None
        try:
            raw = socket.create_connection((address, 443), timeout=timeout_seconds)
            tls = context.wrap_socket(raw, server_hostname=domain)
            result["tls_present"] = True
            result["tls_version"] = tls.version()
            result["certificate_matches_hostname"] = True
            request = (
                f"HEAD / HTTP/1.1\r\n"
                f"Host: {domain}\r\n"
                "User-Agent: Ithute-Domain-Intelligence/1.0\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            tls.sendall(request)
            line = tls.makefile("rb", buffering=0).readline(512).decode("latin-1", "replace").strip()
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                result["https_status"] = int(parts[1])
            return result
        except (OSError, ssl.SSLError, ValueError):
            continue
        finally:
            try:
                if tls is not None:
                    tls.close()
                elif raw is not None:
                    raw.close()
            except OSError:
                pass
    return result


def collect_domain_evidence(domain: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    normalized = _safe_domain(domain)
    public_addresses = _public_addresses(normalized)
    mx = _dns_values(normalized, "MX")
    ns = _dns_values(normalized, "NS")
    txt = _dns_values(normalized, "TXT")
    created_at, rdap = _rdap_created_at(normalized, timeout_seconds)
    tls_http = _tls_http_probe(normalized, public_addresses, timeout_seconds)

    age_days = None
    if created_at is not None:
        age_days = max(0, (datetime.now(timezone.utc) - created_at).days)

    has_spf = any("v=spf1" in value.lower() for value in txt)
    has_dmarc = bool(_dns_values(f"_dmarc.{normalized}", "TXT"))
    infrastructure = {
        "mx_present": bool(mx),
        "ns_present": bool(ns),
        "spf_present": has_spf,
        "dmarc_present": has_dmarc,
        "https_present": bool(tls_http["tls_present"]),
    }

    return {
        "domain": normalized,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "domain_age_days": age_days,
        "rdap": rdap,
        "dns": {
            "mx": mx,
            "ns": ns,
            "spf_present": has_spf,
            "dmarc_present": has_dmarc,
            "public_addresses": public_addresses,
        },
        "web": tls_http,
        "infrastructure": infrastructure,
        "privacy": {
            "raw_page_content_stored": False,
            "certificate_body_stored": False,
            "rdap_personal_contact_fields_stored": False,
        },
    }


def apply_automatic_enrichment(
    db: Session,
    profile: DomainIntelligenceProfile,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    evidence = collect_domain_evidence(profile.domain, timeout_seconds=timeout_seconds)
    now = datetime.now(timezone.utc)
    profile.domain_age_days = evidence.get("domain_age_days")
    profile.enrichment_source = "automatic:rdap+dns+tls"
    profile.enrichment_checked_at = now

    current = profile.evidence_json if isinstance(profile.evidence_json, dict) else {}
    profile.evidence_json = {
        **current,
        "automatic_enrichment": evidence,
        "raw_message_content_stored": False,
    }

    # Automatic infrastructure evidence is deliberately descriptive. It does
    # not automatically declare an organisation identity to be verified.
    if profile.identity_status in {"", "unverified", None}:
        profile.identity_status = "unverified"

    refresh_domain_profile(profile)
    db.flush()
    return evidence
