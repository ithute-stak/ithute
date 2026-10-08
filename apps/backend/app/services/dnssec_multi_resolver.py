"""Read-only DNSSEC cross-resolver evidence.

A single resolver returning AD=1 is useful evidence, but agreement across two
providers is stronger. This service never modifies DNS or registrar state.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.services.dnssec_resolver_validation import validating_resolver_check

VALIDATING_RESOLVERS = ("1.1.1.1", "8.8.8.8")


def multi_resolver_dnssec_check(domain: str) -> dict:
    with ThreadPoolExecutor(max_workers=len(VALIDATING_RESOLVERS)) as pool:
        results = list(pool.map(lambda ip: validating_resolver_check(domain, resolver_ip=ip), VALIDATING_RESOLVERS))
    states = [str(item.get("state")) for item in results]
    if all(state == "validated" for state in states):
        overall = "validated"
    elif "failure" in states:
        overall = "possible_failure"
    elif "validated" in states:
        overall = "inconsistent"
    elif all(state == "unverified" for state in states):
        overall = "unverified"
    else:
        overall = "inconclusive"
    return {
        "state": overall,
        "results": results,
        "read_only": True,
        "description": "External resolver-reported authentication evidence, not local cryptographic verification.",
    }
