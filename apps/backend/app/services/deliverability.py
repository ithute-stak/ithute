import base64
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.security import encrypt_dkim_secret
from app.services.engine_router import execute_dns

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


def recommended_records(
    domain: str,
    mail_hostname: str,
    selector: str,
    public_key_b64: str,
    *,
    mta_sts_id: str | None = None,
    mta_sts_ip: str | None = None,
    tls_report_address: str | None = None,
) -> list[dict]:
    records = [
        {"name": domain, "type": "MX", "value": f"10 {mail_hostname}.", "purpose": "mail-routing"},
        {"name": domain, "type": "TXT", "value": "v=spf1 mx -all", "purpose": "spf"},
        {"name": f"{selector}._domainkey.{domain}", "type": "TXT", "value": f"v=DKIM1; k=rsa; p={public_key_b64}", "purpose": "dkim"},
        {"name": f"_dmarc.{domain}", "type": "TXT", "value": "v=DMARC1; p=quarantine; adkim=s; aspf=s; pct=100", "purpose": "dmarc"},
    ]
    if mta_sts_id:
        records.append({"name": f"_mta-sts.{domain}", "type": "TXT", "value": f"v=STSv1; id={mta_sts_id}", "purpose": "mta-sts"})
    if mta_sts_ip:
        records.append({"name": f"mta-sts.{domain}", "type": "A", "value": mta_sts_ip, "purpose": "mta-sts-host"})
    if tls_report_address:
        records.append({
            "name": f"_smtp._tls.{domain}",
            "type": "TXT",
            "value": f"v=TLSRPTv1; rua=mailto:{tls_report_address}",
            "purpose": "tls-rpt",
        })
    return records


def _dns_values(name: str, rtype: str) -> list[str]:
    execution = execute_dns(
        [{"id": "lookup", "name": name, "type": rtype, "timeout_ms": 5000}],
        concurrency=1,
    )
    results = execution.value.get("results", []) if isinstance(execution.value, dict) else []
    if not results:
        return []
    values = results[0].get("values") if isinstance(results[0], dict) else []
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _txt_values(name: str) -> list[str]:
    return _dns_values(name, "TXT")


def _mx_hosts(domain: str) -> list[str]:
    hosts: list[str] = []
    for value in _dns_values(domain, "MX"):
        _, separator, host = value.partition(" ")
        hosts.append((host if separator else value).rstrip(".").lower())
    return hosts


def _host_addresses(hostname: str) -> list[str]:
    return _dns_values(hostname, "A") + _dns_values(hostname, "AAAA")


def _ptr_hosts(public_ip: str) -> list[str]:
    return [value.rstrip(".").lower() for value in _dns_values(public_ip, "PTR")]

def dns_readiness(
    domain: str,
    mail_hostname: str,
    selector: str,
    public_key_b64: str,
    *,
    mta_sts_id: str | None = None,
    mta_sts_ip: str | None = None,
    tls_report_address: str | None = None,
) -> dict:
    records = recommended_records(
        domain,
        mail_hostname,
        selector,
        public_key_b64,
        mta_sts_id=mta_sts_id,
        mta_sts_ip=mta_sts_ip,
        tls_report_address=tls_report_address,
    )
    mx_hosts = _mx_hosts(domain)
    txt_root = _txt_values(domain)
    txt_dkim = _txt_values(f"{selector}._domainkey.{domain}")
    txt_dmarc = _txt_values(f"_dmarc.{domain}")
    txt_mta_sts = _txt_values(f"_mta-sts.{domain}") if mta_sts_id else []
    txt_tls_rpt = _txt_values(f"_smtp._tls.{domain}") if tls_report_address else []
    mta_sts_addresses = _host_addresses(f"mta-sts.{domain}") if mta_sts_ip else []
    checks = {
        "mx": mail_hostname.rstrip(".").lower() in mx_hosts,
        "spf": any(value == "v=spf1 mx -all" for value in txt_root),
        "dkim": any(value == f"v=DKIM1; k=rsa; p={public_key_b64}" for value in txt_dkim),
        "dmarc": any(value.startswith("v=DMARC1;") for value in txt_dmarc),
    }
    if mta_sts_id:
        checks["mta_sts"] = any(value == f"v=STSv1; id={mta_sts_id}" for value in txt_mta_sts)
    if mta_sts_ip:
        checks["mta_sts_host"] = mta_sts_ip in mta_sts_addresses
    if tls_report_address:
        expected_tls_rpt = f"v=TLSRPTv1; rua=mailto:{tls_report_address}"
        checks["tls_rpt"] = any(value == expected_tls_rpt for value in txt_tls_rpt)
    return {"ready": all(checks.values()), "checks": checks, "recommended_records": records}


def deliverability_readiness(
    domain: str,
    mail_hostname: str,
    selector: str,
    public_key_b64: str,
    *,
    mta_sts_id: str | None = None,
    mta_sts_ip: str | None = None,
    tls_report_address: str | None = None,
) -> dict:
    """Stable public service API used by the deliverability routes."""
    return dns_readiness(
        domain,
        mail_hostname,
        selector,
        public_key_b64,
        mta_sts_id=mta_sts_id,
        mta_sts_ip=mta_sts_ip,
        tls_report_address=tls_report_address,
    )


def dmarc_policy_status(domain: str) -> dict:
    values = [value for value in _txt_values(f"_dmarc.{domain}") if value.startswith("v=DMARC1;")]
    if not values:
        return {
            "published": False,
            "policy": None,
            "pct": None,
            "adkim": None,
            "aspf": None,
            "reject_enforced": False,
            "raw": [],
        }
    raw = values[0]
    tags: dict[str, str] = {}
    for part in raw.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep:
            tags[key.strip().lower()] = value.strip().lower()
    policy = tags.get("p")
    try:
        pct = int(tags.get("pct", "100"))
    except ValueError:
        pct = 0
    return {
        "published": True,
        "policy": policy,
        "pct": pct,
        "adkim": tags.get("adkim"),
        "aspf": tags.get("aspf"),
        "reject_enforced": policy == "reject" and pct == 100,
        "raw": values,
    }


def dmarc_reject_record(domain: str, report_address: str | None = None) -> dict:
    value = "v=DMARC1; p=reject; adkim=s; aspf=s; pct=100"
    if report_address:
        value += f"; rua=mailto:{report_address}"
    return {
        "name": f"_dmarc.{domain}",
        "type": "TXT",
        "value": value,
        "purpose": "dmarc",
    }


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
