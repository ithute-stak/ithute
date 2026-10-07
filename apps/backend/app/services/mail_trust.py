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
    allowed = {registrable_hint(item) for item in (allowed_domains or set()) if item}
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
            if allowed and root not in allowed:
                reasons.append("outside_trusted_sender_domains")
            elif not allowed and sender_root and root != sender_root:
                reasons.append("different_from_sender_domain")

        suspicious += 1 if reasons else 0
        rows.append({
            "url": clean,
            "host": host,
            "registrable_domain": root,
            "trusted_domain_match": bool(host and allowed and root in allowed),
            "reasons": reasons,
        })

    return {
        "count": len(rows),
        "suspicious_count": suspicious,
        "items": rows,
    }


def trusted_sender_evidence(message: dict[str, Any]) -> dict[str, Any]:
    auth = authentication_evidence(message)
    sender = auth["sender"]
    registry = ITHUTE_SYSTEM_SENDERS.get(sender)
    allowed_domains = set(registry.get("allowed_link_domains") or set()) if registry else set()
    urls = inspect_urls(message, sender_domain=auth["sender_domain"], allowed_domains=allowed_domains)

    registry_match = registry is not None
    verified = bool(
        registry_match
        and auth["authenticated"]
        and urls["suspicious_count"] == 0
    )

    if registry_match and auth["any_failure"]:
        state = "registry_sender_auth_failed"
    elif verified:
        state = "verified_system_sender"
    elif registry_match:
        state = "registry_sender_unverified"
    else:
        state = "not_registered"

    return {
        "state": state,
        "verified": verified,
        "registry_match": registry_match,
        "sender": sender,
        "display_name": str(registry.get("name") or "") if registry else "",
        "category": str(registry.get("category") or "") if registry else "",
        "authentication": auth,
        "url_intelligence": urls,
        "security_path_present": any(
            str(item.get("url") or "").lower().find(path) >= 0
            for item in urls["items"]
            for path in SECURITY_PATH_HINTS
        ),
        "trust_reason": (
            "registered sender + SPF/DKIM/DMARC pass + trusted links"
            if verified
            else "registry identity requires authenticated headers and trusted links"
            if registry_match
            else "sender is not in the Ithute system-sender registry"
        ),
    }
