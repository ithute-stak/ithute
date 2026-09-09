import hashlib
import json
import re
import secrets
from datetime import datetime, timezone

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rdatatype
import dns.resolver

from app.core.config import settings
from app.models.domains import Domain, DomainEvent, DomainStatus, DomainVerificationAttempt

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_VERIFICATION_PREFIX = "mailbox-dns-verification="


def normalize_domain(value: str) -> tuple[str, str]:
    raw = value.strip().rstrip(".")
    lowered = raw.lower()
    if "://" in lowered or "/" in lowered or "@" in lowered or lowered.startswith("*."):
        raise ValueError("Enter a bare domain name without scheme, path, email, or wildcard")
    try:
        ascii_name = lowered.encode("idna").decode("ascii")
        unicode_name = ascii_name.encode("ascii").decode("idna")
    except UnicodeError as exc:
        raise ValueError("Invalid internationalized domain name") from exc
    if len(ascii_name) > 253 or "." not in ascii_name:
        raise ValueError("A registrable domain name is required")
    labels = ascii_name.split(".")
    if any(not label or len(label) > 63 or not _LABEL.fullmatch(label) for label in labels):
        raise ValueError("Invalid domain label")
    if labels[-1].isdigit() or len(labels[-1]) < 2:
        raise ValueError("Invalid top-level domain")
    return ascii_name, unicode_name


def new_verification_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verification_value(token: str) -> str:
    return f"{_VERIFICATION_PREFIX}{token}"


def record_name(ascii_name: str) -> str:
    return f"_mailbox-dns-verification.{ascii_name}"


def resolve_txt(name: str) -> list[str]:
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    answers = resolver.resolve(name, "TXT")
    values: list[str] = []
    for answer in answers:
        chunks = getattr(answer, "strings", None)
        if chunks:
            values.append(b"".join(chunks).decode("utf-8", errors="replace"))
        else:
            values.append(str(answer).strip('"'))
    return values


def _normalize_nameservers(values) -> list[str]:
    return sorted({str(value).strip().rstrip(".").lower() for value in values if str(value).strip()})


def resolve_delegated_ns(name: str) -> list[str]:
    """Read a domain's NS delegation from its parent zone.

    A normal recursive NS lookup can fail while a newly delegated domain is still
    a lame delegation (the child zone is not live yet). Ownership verification
    must therefore inspect the parent referral directly. Changing that parent
    delegation requires registrar/registry control and is valid ownership proof.
    """
    target = name.strip().rstrip(".").lower()
    if "." not in target:
        return []
    parent = target.split(".", 1)[1]

    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 3.0
    resolver.lifetime = 5.0
    parent_ns = [str(answer.target).rstrip(".") for answer in resolver.resolve(parent, "NS", search=False)]

    observed: set[str] = set()
    query = dns.message.make_query(target, dns.rdatatype.NS)
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


def _verification_candidates(observed: list[str], raw_token: str | None = None) -> list[str]:
    candidates: list[str] = []
    if raw_token:
        candidates.append(raw_token)
    for value in observed:
        if not value.startswith(_VERIFICATION_PREFIX):
            continue
        candidate = value[len(_VERIFICATION_PREFIX):].strip()
        if 20 <= len(candidate) <= 200:
            candidates.append(candidate)
    return candidates


def verify_domain(
    domain: Domain,
    raw_token: str | None,
    actor_user_id,
    db,
    resolver=resolve_txt,
    nameserver_resolver=resolve_delegated_ns,
) -> tuple[bool, list[str], str | None]:
    observed: list[str] = []
    error: str | None = None
    success = False

    # Preferred flow: a one-time TXT record at the existing DNS provider.
    try:
        observed = resolver(domain.verification_record_name)
        for candidate in _verification_candidates(observed, raw_token):
            if not secrets.compare_digest(token_hash(candidate), domain.verification_token_hash):
                continue
            if verification_value(candidate) in observed:
                success = True
                break
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
        error = exc.__class__.__name__
    except Exception as exc:
        error = f"resolver_error:{exc.__class__.__name__}"

    # Registrar-only fallback for platform DNS: if the owner cannot publish TXT
    # but can change nameservers, delegation to BOTH configured Ithute servers is
    # itself proof of registrar control. Inspect the parent referral so this also
    # works before the child PowerDNS zone is authoritative.
    dns_mode = getattr(domain, "dns_mode", None)
    dns_mode_value = getattr(dns_mode, "value", dns_mode)
    ascii_name = str(getattr(domain, "ascii_name", "") or "").strip().rstrip(".").lower()
    expected_ns = _normalize_nameservers([settings.nameserver_1, settings.nameserver_2])
    if not success and dns_mode_value == "platform" and ascii_name and len(set(expected_ns)) >= 2:
        try:
            delegated_ns = _normalize_nameservers(nameserver_resolver(ascii_name))
            observed.extend(f"NS:{value}" for value in delegated_ns)
            if set(expected_ns).issubset(set(delegated_ns)):
                success = True
                error = None
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            if error is None:
                error = f"delegation_{exc.__class__.__name__}"
        except Exception as exc:
            if error is None:
                error = f"delegation_resolver_error:{exc.__class__.__name__}"

    db.add(DomainVerificationAttempt(
        domain_id=domain.id,
        actor_user_id=actor_user_id,
        success=success,
        observed_values_json=json.dumps(observed),
        error=error,
    ))
    if success:
        domain.status = DomainStatus.verified
        domain.ownership_verified_at = datetime.now(timezone.utc)
        # Invalidate the disclosed challenge immediately. A later re-verification
        # must explicitly generate a fresh challenge.
        domain.verification_token_hash = token_hash(new_verification_token())
        domain.verification_token_hint = "verified"
    return success, observed, error


def add_domain_event(db, domain: Domain, actor_user_id, event_type: str, metadata: dict | None = None) -> None:
    db.add(DomainEvent(
        domain_id=domain.id,
        tenant_id=domain.tenant_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))
