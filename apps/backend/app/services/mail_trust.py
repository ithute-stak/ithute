from __future__ import annotations

import ipaddress
import re
from email.utils import getaddresses
from typing import Any
from urllib.parse import urlparse

AUTH_RESULT_RE = re.compile(r"\b(spf|dkim|dmarc|arc)=(pass|fail|softfail|neutral|none|temperror|permerror)\b", re.IGNORECASE)

# First-party identities are intentionally explicit. Matching the From address
# alone never creates trust: registry membership must be combined with message
# authentication evidence before a message is considered verified.
ITHUTE_SYSTEM_SENDERS: dict[str, dict[str, Any]] = {
    "auth@ithute.co.ls": {
        "name": "Ithute Identity & Account Security",
        "category": "account_security",
        "allowed_link_domains": {"ithute.co.ls"},
    },
    "info@ithute.co.ls": {
        "name": "Ithute Official Information",
        "category": "official_information",
        "allowed_link_domains": {"ithute.co.ls"},
    },
    "supperadmin@ithute.co.ls": {
        "name": "Ithute Platform Administration",
        "category": "platform_administration",
        "allowed_link_domains": {"ithute.co.ls"},
    },
    "thekoetlisi@ithute.co.ls": {
        "name": "Ithute Platform Operations",
        "category": "platform_operations",
        "allowed_link_domains": {"ithute.co.ls"},
    },
}

SECURITY_PATH_HINTS = (
    "/reset-password",
    "/forgot-password",
    "/security",
    "/login",
    "/auth",
)


def _address(value: Any) -> str:
    addresses = [addr.lower() for _, addr in getaddresses([str(value or "")]) if addr]
    return addresses[0] if addresses else ""


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower().strip(".") if "@" in address else ""


def registrable_hint(host: str) -> str:
    host = str(host or "").lower().strip(".")
    labels = [label for label in host.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def authentication_evidence(message: dict[str, Any]) -> dict[str, Any]:
    raw = str(message.get("authentication_results") or "")
    received_spf = str(message.get("received_spf") or "")
    statuses: dict[str, str] = {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown", "arc": "unknown"}

    for mechanism, result in AUTH_RESULT_RE.findall(raw):
        statuses[mechanism.lower()] = result.lower()

    lowered_spf = received_spf.lower().strip()
    if statuses["spf"] == "unknown":
        for candidate in ("pass", "fail", "softfail", "neutral", "none", "temperror", "permerror"):
            if lowered_spf.startswith(candidate):
                statuses["spf"] = candidate
                break

    sender = _address(message.get("from"))
    sender_domain = domain_of(sender)
    authenticated = all(statuses[name] == "pass" for name in ("spf", "dkim", "dmarc"))
    any_failure = any(statuses[name] in {"fail", "softfail", "permerror"} for name in ("spf", "dkim", "dmarc"))

    return {
        "sender": sender,
        "sender_domain": sender_domain,
        "spf": statuses["spf"],
        "dkim": statuses["dkim"],
        "dmarc": statuses["dmarc"],
        "arc": statuses["arc"],
        "authenticated": authenticated,
        "any_failure": any_failure,
        "evidence_source": "message_headers",
    }


def inspect_urls(message: dict[str, Any], *, sender_domain: str = "", allowed_domains: set[str] | None = None) -> dict[str, Any]:
    text = f"{message.get('subject') or ''}\n{message.get('body_text') or ''}"
    urls = re.findall(r"https?://[^\s<>()\[\]\"']+", text, flags=re.IGNORECASE)
    allowed = {str(item).lower().strip(".") for item in (allowed_domains or set()) if item}
    sender_root = registrable_hint(sender_domain)
    rows: list[dict[str, Any]] = []
    suspicious = 0

    for raw in urls[:50]:
        clean = raw.rstrip(".,;:!?")
        try:
            parsed = urlparse(clean)
            host = (parsed.hostname or "").lower().strip(".")
        except ValueError:
            host = ""

        root = registrable_hint(host)
        reasons: list[str] = []
        if not host:
            reasons.append("invalid_url")
        else:
            try:
                ipaddress.ip_address(host)
                reasons.append("ip_literal_host")
            except ValueError:
                pass
            if parsed.scheme.lower() != "https":
                reasons.append("not_https")
            if parsed.username or parsed.password:
                reasons.append("userinfo_in_url")
            if "xn--" in host:
                reasons.append("punycode_hostname")
            trusted_allowed_domain = any(host == item or host.endswith(f".{item}") for item in allowed)
            if allowed and not trusted_allowed_domain:
                reasons.append("outside_trusted_sender_domains")
            elif not allowed and sender_root and root != sender_root:
                reasons.append("different_from_sender_domain")

        suspicious += 1 if reasons else 0
        rows.append({
            "url": clean,
            "host": host,
            "registrable_domain": root,
            "trusted_domain_match": bool(host and allowed and any(host == item or host.endswith(f".{item}") for item in allowed)),
            "reasons": reasons,
        })

    return {
        "count": len(rows),
        "suspicious_count": suspicious,
        "items": rows,
    }


def _normalize_registry_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(entry.get("name") or "").strip(),
        "category": str(entry.get("category") or "business_partner").strip() or "business_partner",
        "sender_addresses": {
            str(item or "").strip().lower()
            for item in (entry.get("sender_addresses") or [])
            if str(item or "").strip()
        },
        "sender_domains": {
            str(item or "").strip().lower().strip(".")
            for item in (entry.get("sender_domains") or [])
            if str(item or "").strip()
        },
        "allowed_link_domains": {
            str(item or "").strip().lower().strip(".")
            for item in (entry.get("allowed_link_domains") or [])
            if str(item or "").strip()
        },
        "require_spf": bool(entry.get("require_spf", True)),
        "require_dkim": bool(entry.get("require_dkim", True)),
        "require_dmarc": bool(entry.get("require_dmarc", True)),
        "source": str(entry.get("source") or "tenant_registry"),
    }


def _tenant_registry_match(sender: str, sender_domain: str, entries: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for raw in entries or []:
        entry = _normalize_registry_entry(raw)
        if sender in entry["sender_addresses"] or any(
            sender_domain == domain or sender_domain.endswith(f".{domain}")
            for domain in entry["sender_domains"]
        ):
            return entry
    return None


def trusted_sender_evidence(
    message: dict[str, Any],
    *,
    registry_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    auth = authentication_evidence(message)
    sender = auth["sender"]
    sender_domain = auth["sender_domain"]

    system = ITHUTE_SYSTEM_SENDERS.get(sender)
    tenant = _tenant_registry_match(sender, sender_domain, registry_entries)

    if system is not None:
        # First-party security identities are immutable and cannot be weakened by
        # a tenant-defined profile for the same address or domain.
        registry = {
            **system,
            "allowed_link_domains": set(system.get("allowed_link_domains") or set()),
        }
        registry_source = "ithute_system_registry"
        required = {"spf": True, "dkim": True, "dmarc": True}
    elif tenant is not None:
        registry = tenant
        registry_source = "tenant_registry"
        required = {
            "spf": bool(tenant["require_spf"]),
            "dkim": bool(tenant["require_dkim"]),
            "dmarc": bool(tenant["require_dmarc"]),
        }
    else:
        registry = None
        registry_source = "none"
        required = {"spf": False, "dkim": False, "dmarc": False}

    allowed_domains = set(registry.get("allowed_link_domains") or set()) if registry else set()
    urls = inspect_urls(message, sender_domain=sender_domain, allowed_domains=allowed_domains)

    required_failures = [
        mechanism
        for mechanism, is_required in required.items()
        if is_required and auth.get(mechanism) in {"fail", "softfail", "permerror"}
    ]
    required_missing = [
        mechanism
        for mechanism, is_required in required.items()
        if is_required and auth.get(mechanism) != "pass"
    ]

    registry_match = registry is not None
    verified = bool(
        registry_match
        and not required_missing
        and urls["suspicious_count"] == 0
    )

    if registry_match and required_failures:
        state = "registry_sender_auth_failed"
    elif verified:
        state = "verified_system_sender" if registry_source == "ithute_system_registry" else "verified_trusted_sender"
    elif registry_match:
        state = "registry_sender_unverified"
    else:
        state = "not_registered"

    return {
        "state": state,
        "verified": verified,
        "registry_match": registry_match,
        "registry_source": registry_source,
        "sender": sender,
        "display_name": str(registry.get("name") or "") if registry else "",
        "category": str(registry.get("category") or "") if registry else "",
        "authentication": auth,
        "authentication_policy": {
            "required": [name for name, enabled in required.items() if enabled],
            "missing_or_failed": required_missing,
        },
        "url_intelligence": urls,
        "security_path_present": any(
            str(item.get("url") or "").lower().find(path) >= 0
            for item in urls["items"]
            for path in SECURITY_PATH_HINTS
        ),
        "trust_reason": (
            "registered sender + required authentication pass + trusted links"
            if verified
            else "registered sender failed required authentication"
            if registry_match and required_failures
            else "registered sender requires required authentication and trusted links"
            if registry_match
            else "sender is not in the trusted sender registry"
        ),
    }
