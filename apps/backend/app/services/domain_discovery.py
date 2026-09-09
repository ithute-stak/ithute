from __future__ import annotations

from collections.abc import Callable, Iterable

import dns.exception
import dns.resolver


ResolverFn = Callable[[str], Iterable[str]]
RecordResolverFn = Callable[[str, str], Iterable[str]]


def _normalize_nameservers(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip().rstrip(".").lower() for value in values if str(value).strip()})


def platform_nameservers_ready(nameservers: Iterable[str]) -> bool:
    values = _normalize_nameservers(nameservers)
    if len(values) < 2 or len(set(values)) < 2:
        return False
    blocked_suffixes = (".example", ".test", ".local", ".localhost", ".invalid")
    for value in values:
        if "." not in value or value == "localhost" or value.endswith(blocked_suffixes):
            return False
        if "example." in value or value.startswith("example."):
            return False
    return True


def infer_nameserver_provider(nameservers: Iterable[str], platform_nameservers: Iterable[str] = ()) -> str | None:
    current = _normalize_nameservers(nameservers)
    platform = set(_normalize_nameservers(platform_nameservers))
    if not current:
        return None
    if platform_nameservers_ready(platform) and set(current) == platform:
        return "Mailbox DNS / PowerDNS"
    if any("cloudflare" in item for item in current):
        return "Cloudflare"
    if any("zeecom" in item for item in current):
        return "Zeecom Technologies"
    if any("awsdns" in item for item in current):
        return "Amazon Route 53"
    if any("azure-dns" in item for item in current):
        return "Microsoft Azure DNS"
    if any("googledomains" in item or "google.com" in item for item in current):
        return "Google DNS"
    if any("digitalocean" in item for item in current):
        return "DigitalOcean DNS"
    return "External DNS provider"


def _system_resolve(name: str) -> list[str]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 3.0
    resolver.lifetime = 5.0
    answers = resolver.resolve(name, "NS", search=False)
    return [str(answer.target) for answer in answers]


def _system_resolve_record(name: str, record_type: str) -> list[str]:
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 3.0
    resolver.lifetime = 5.0
    answers = resolver.resolve(name, record_type, search=False)
    return [str(answer).strip() for answer in answers]


def inspect_existing_records(name: str, resolve_fn: RecordResolverFn | None = None) -> dict:
    """Detect whether a domain already carries customer-facing DNS records.

    NS and SOA do not count because registrars commonly create those for a newly
    registered/parked domain. A/AAAA/CNAME/MX/TXT records indicate an existing
    DNS lifecycle that should be preserved and verified before nameserver cutover.
    """
    resolver = resolve_fn or _system_resolve_record
    found: list[str] = []
    lookup_errors: list[str] = []
    for record_type in ("A", "AAAA", "CNAME", "MX", "TXT"):
        try:
            values = [str(value).strip() for value in resolver(name, record_type) if str(value).strip()]
            if values:
                found.append(record_type)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            continue
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            lookup_errors.append(exc.__class__.__name__)
        except Exception as exc:
            lookup_errors.append(f"resolver_error:{exc.__class__.__name__}")

    return {
        "has_existing_dns_records": bool(found),
        "existing_record_types": found,
        "record_lookup_status": "found" if found else ("resolver_error" if lookup_errors else "none"),
        "record_lookup_errors": sorted(set(lookup_errors)),
    }


def inspect_nameservers(
    name: str,
    platform_nameservers: Iterable[str],
    resolve_fn: ResolverFn | None = None,
) -> dict:
    """Inspect currently published authoritative NS records for a domain.

    The result deliberately distinguishes a missing delegation from a temporary
    resolver failure so the onboarding UI does not tell an operator to change
    registrar settings based on an unreliable lookup.
    """
    resolver = resolve_fn or _system_resolve
    platform = _normalize_nameservers(platform_nameservers)
    platform_ready = platform_nameservers_ready(platform)
    try:
        current = _normalize_nameservers(resolver(name))
        status = "found" if current else "no_nameservers"
        detail = None if current else "No authoritative nameservers were returned for this domain."
    except dns.resolver.NXDOMAIN:
        current = []
        status = "nxdomain"
        detail = "The domain does not currently exist in public DNS. Check that it is registered and typed correctly."
    except dns.resolver.NoAnswer:
        current = []
        status = "no_nameservers"
        detail = "The domain exists, but no authoritative NS records were returned."
    except dns.resolver.NoNameservers:
        current = []
        status = "resolver_error"
        detail = "Public DNS could not obtain an authoritative answer for this domain."
    except dns.exception.Timeout:
        current = []
        status = "timeout"
        detail = "The public nameserver lookup timed out. Retry before changing registrar settings."
    except Exception as exc:  # keep onboarding available if the host resolver has a transient problem
        current = []
        status = "resolver_error"
        detail = f"Nameserver lookup failed: {str(exc)[:180]}"

    return {
        "lookup_status": status,
        "lookup_detail": detail,
        "current_nameservers": current,
        "current_provider": infer_nameserver_provider(current, platform),
        "platform_nameservers": platform if platform_ready else [],
        "platform_nameservers_configured": platform_ready,
        "already_on_platform_nameservers": bool(platform_ready and current and set(current) == set(platform)),
    }
