"""Pure DNSSEC incident assessment for monitoring workers.

Produces reviewable findings only; never mutates DNS, opens incidents or sends
notifications. Monitoring persistence and dispatch are separate follow-up work.
"""
from __future__ import annotations


def classify_dnssec_observation(readiness: dict, resolver: dict) -> dict:
    """Classify observed state without confusing missing evidence with DNSSEC breakage."""
    state = str(resolver.get("state") or "error")
    steps = {item.get("key"): item for item in readiness.get("steps", [])}
    parent = steps.get("parent", {}).get("state")
    delegation = steps.get("delegation", {}).get("state")
    signing = steps.get("signing", {}).get("state")

    if state == "validated":
        return {"severity": "healthy", "code": "DNSSEC_VALIDATED",
                "summary": "Validating resolver reports an authenticated response.", "remediation": "none"}
    if state == "failure":
        return {"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL",
                "summary": "Validating resolver returned SERVFAIL; DNSSEC breakage is one possible cause.",
                "remediation": "investigate"}
    if delegation == "blocked":
        return {"severity": "warning", "code": "DNS_DELEGATION_UNCERTAIN",
                "summary": "Public delegation checks failed; DNSSEC condition is not verified.",
                "remediation": "investigate"}
    if parent == "blocked":
        return {"severity": "unknown", "code": "PARENT_DS_LOOKUP_UNCERTAIN",
                "summary": "Parent DS observations are inconclusive.",
                "remediation": "retry"}
    if signing != "complete":
        return {"severity": "warning" if parent == "complete" else "info",
                "code": "DNSSEC_SIGNING_DISABLED",
                "summary": "Authoritative zone DNSSEC signing is not enabled.",
                "remediation": "investigate" if parent == "complete" else "review"}
    if parent != "complete":
        return {"severity": "warning", "code": "DNSSEC_PARENT_DS_UNVERIFIED",
                "summary": "The expected parent DS record has not been verified.",
                "remediation": "review"}
    if state == "unverified":
        return {"severity": "warning", "code": "DNSSEC_RESOLVER_UNVERIFIED",
                "summary": "The validating resolver did not set the authenticated-data flag.",
                "remediation": "investigate"}
    return {"severity": "unknown", "code": "DNSSEC_RESOLVER_UNAVAILABLE",
            "summary": "Resolver validation is unavailable or inconclusive.",
            "remediation": "retry"}
