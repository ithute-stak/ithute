from __future__ import annotations

from collections.abc import Callable, Iterable

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rdatatype
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


def _system_resolve_parent_delegation(name: str) -> list[str]:
    """Read the registrar/registry NS delegation even when the child zone is lame.

    Recursive NS lookups can raise NoNameservers for a newly registered domain
    whose registrar has already published nameservers but whose child DNS is not
    answering yet. Cloud-style onboarding still needs to show that delegation,
    so ask the parent zone directly and read its NS referral.
    """
    target = name.strip().rstrip(".").lower()
    if "." not in target:
        return []
    parent = target.split(".", 1)[1]

    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 3.0
    resolver.lifetime = 5.0
    parent_ns = [str(answer.target).rstrip(".") for answer in resolver.resolve(parent, "NS", search=False)]

    query = dns.message.make_query(target, dns.rdatatype.NS)
    observed: set[str] = set()
    for host in parent_ns:
        addresses: list[str] = []
        for rtype in ("A", "AAAA"):
            try:
                addresses.extend(str(answer) for answer in resolver.resolve(host, rtype, search=False))
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout):
                continue
        for address in addresses:
            try:
                response = dns.query.udp(query, address, timeout=3.0)
                if response.flags & dns.flags.TC:
                    response = dns.query.tcp(query, address, timeout=3.0)
            except (OSError, dns.exception.DNSException):
                continue
            for rrset in [*response.answer, *response.authority]:
                if rrset.rdtype != dns.rdatatype.NS:
                    continue
                if rrset.name.to_text().rstrip(".").lower() != target:
                    continue
                for item in rrset:
                    destination = getattr(item, "target", None)
                    if destination is not None:
                        observed.add(str(destination).rstrip(".").lower())
            if observed:
                return sorted(observed)
    return sorted(observed)


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
    DNS lifecycle that should be copied into a staged PowerDNS zone before a
    nameserver cutover. They no longer force TXT ownership proof for managed DNS.
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
    parent_resolve_fn: ResolverFn | None = None,
) -> dict:
    """Inspect currently published nameservers for a domain.

    Prefer a normal recursive lookup, then fall back to the parent-zone referral
    when a newly registered or lame child zone cannot answer. The parent referral
    is the registrar/registry delegation and is therefore the most useful signal
    for Cloudflare-style onboarding and ownership verification.
    """
    resolver = resolve_fn or _system_resolve
    parent_resolver = parent_resolve_fn or _system_resolve_parent_delegation
    platform = _normalize_nameservers(platform_nameservers)
    platform_ready = platform_nameservers_ready(platform)
    source: str | None = None

    try:
        current = _normalize_nameservers(resolver(name))
        status = "found" if current else "no_nameservers"
        detail = None if current else "No authoritative nameservers were returned for this domain."
        source = "recursive" if current else None
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
        detail = "The public nameserver lookup timed out."
    except Exception as exc:  # keep onboarding available if the host resolver has a transient problem
        current = []
        status = "resolver_error"
        detail = f"Nameserver lookup failed: {str(exc)[:180]}"

    # A broken/empty child zone must not hide registrar nameservers. This is
    # particularly common immediately after buying a domain from a registrar.
    if not current and status != "nxdomain":
        try:
            delegated = _normalize_nameservers(parent_resolver(name))
        except Exception:
            delegated = []
        if delegated:
            current = delegated
            status = "found"
            source = "parent"
            detail = "Nameservers were discovered from the parent-zone registrar delegation; the child DNS is not answering normally yet."

    return {
        "lookup_status": status,
        "lookup_detail": detail,
        "delegation_source": source,
        "current_nameservers": current,
        "current_provider": infer_nameserver_provider(current, platform),
        "platform_nameservers": platform if platform_ready else [],
        "platform_nameservers_configured": platform_ready,
        "already_on_platform_nameservers": bool(platform_ready and current and set(current) == set(platform)),
    }
