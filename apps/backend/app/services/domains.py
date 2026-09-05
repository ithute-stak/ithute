import hashlib
import json
import re
import secrets
from datetime import datetime, timezone

import dns.exception
import dns.resolver

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


def verify_domain(domain: Domain, raw_token: str | None, actor_user_id, db, resolver=resolve_txt) -> tuple[bool, list[str], str | None]:
    observed: list[str] = []
    error: str | None = None
    success = False
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
