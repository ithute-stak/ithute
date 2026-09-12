import base64
import re

import dns.resolver
import dns.reversename
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.security import encrypt_dkim_secret

SELECTOR_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_selector(value: str) -> str:
    selector = value.strip().lower()
    if not SELECTOR_RE.fullmatch(selector):
        raise ValueError("DKIM selector must contain only lowercase letters, digits and hyphens")
    return selector


def generate_dkim_material() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return encrypt_dkim_secret(private_pem), base64.b64encode(public_der).decode()


def recommended_records(domain: str, mail_hostname: str, selector: str, public_key_b64: str) -> list[dict]:
    return [
        {"name": domain, "type": "MX", "value": f"10 {mail_hostname}.", "purpose": "mail-routing"},
        {"name": domain, "type": "TXT", "value": "v=spf1 mx -all", "purpose": "spf"},
        {"name": f"{selector}._domainkey.{domain}", "type": "TXT", "value": f"v=DKIM1; k=rsa; p={public_key_b64}", "purpose": "dkim"},
        {"name": f"_dmarc.{domain}", "type": "TXT", "value": "v=DMARC1; p=quarantine; adkim=s; aspf=s; pct=100", "purpose": "dmarc"},
    ]


def _txt_values(name: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5)
    except Exception:
        return []
    values = []
    for answer in answers:
        values.append("".join(part.decode() if isinstance(part, bytes) else str(part) for part in answer.strings))
    return values


def _mx_hosts(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
    except Exception:
        return []
    return [str(answer.exchange).rstrip(".").lower() for answer in answers]


def _host_addresses(hostname: str) -> list[str]:
    values: list[str] = []
    for rrtype in ("A", "AAAA"):
        try:
            answers = dns.resolver.resolve(hostname, rrtype, lifetime=5)
        except Exception:
            continue
        values.extend(str(answer).strip() for answer in answers)
    return values


def _ptr_hosts(public_ip: str) -> list[str]:
    try:
        reverse_name = dns.reversename.from_address(public_ip)
        answers = dns.resolver.resolve(reverse_name, "PTR", lifetime=5)
    except Exception:
        return []
    return [str(answer.target).rstrip(".").lower() for answer in answers]


def dns_readiness(domain: str, mail_hostname: str, selector: str, public_key_b64: str) -> dict:
    records = recommended_records(domain, mail_hostname, selector, public_key_b64)
    mx_hosts = _mx_hosts(domain)
    txt_root = _txt_values(domain)
    txt_dkim = _txt_values(f"{selector}._domainkey.{domain}")
    txt_dmarc = _txt_values(f"_dmarc.{domain}")
    checks = {
        "mx": mail_hostname.rstrip(".").lower() in mx_hosts,
        "spf": any(value == "v=spf1 mx -all" for value in txt_root),
        "dkim": any(value == f"v=DKIM1; k=rsa; p={public_key_b64}" for value in txt_dkim),
        "dmarc": any(value.startswith("v=DMARC1;") for value in txt_dmarc),
    }
    return {"ready": all(checks.values()), "checks": checks, "recommended_records": records}


def deliverability_readiness(domain: str, mail_hostname: str, selector: str, public_key_b64: str) -> dict:
    """Stable public service API used by the deliverability routes.

    Keep the route-facing name separate from the DNS implementation helper so
    future Phase 10 policy checks can be composed here without breaking older
    callers or the Phase 8/9 regression gates.
    """
    return dns_readiness(domain, mail_hostname, selector, public_key_b64)


def infrastructure_readiness(mail_hostname: str, mail_public_ip: str | None) -> dict:
    hostname = mail_hostname.rstrip(".").lower()
    if not mail_public_ip:
        return {
            "ready": False,
            "checks": {"public_ip_configured": False, "forward_dns": False, "ptr": False, "fcrdns": False},
            "mail_hostname": hostname,
            "public_ip": None,
            "addresses": [],
            "ptr_hosts": [],
        }
    addresses = _host_addresses(hostname)
    ptr_hosts = _ptr_hosts(mail_public_ip)
    checks = {
        "public_ip_configured": True,
        "forward_dns": mail_public_ip in addresses,
        "ptr": hostname in ptr_hosts,
        "fcrdns": hostname in ptr_hosts and mail_public_ip in addresses,
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "mail_hostname": hostname,
        "public_ip": mail_public_ip,
        "addresses": addresses,
        "ptr_hosts": ptr_hosts,
    }
