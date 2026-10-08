"""Read-only DNSSEC check via a validating recursive resolver.

AD=1 is evidence reported by the configured validating resolver, not an
independent local proof. Failure responses must never be interpreted as safe
absence of parent DS records.
"""
from __future__ import annotations

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.rdatatype


def validating_resolver_check(domain: str, resolver_ip: str = "1.1.1.1", timeout: float = 4.0) -> dict:
    query = dns.message.make_query(domain.rstrip(".") + ".", dns.rdatatype.SOA, want_dnssec=True)
    query.flags |= dns.flags.AD
    try:
        response = dns.query.udp(query, resolver_ip, timeout=timeout)
        if response.flags & dns.flags.TC:
            response = dns.query.tcp(query, resolver_ip, timeout=timeout)
    except (dns.exception.DNSException, OSError) as exc:
        return {"state": "error", "authenticated": False, "resolver": resolver_ip,
                "message": f"Resolver query failed: {type(exc).__name__}"}
    code = response.rcode()
    authenticated = bool(response.flags & dns.flags.AD)
    if code == dns.rcode.SERVFAIL:
        state = "failure"
        message = "Validating resolver returned SERVFAIL; broken DNSSEC is one possible cause."
    elif code != dns.rcode.NOERROR:
        state = "error"
        message = f"Validating resolver returned {dns.rcode.to_text(code)}."
    elif authenticated:
        state = "validated"
        message = "The configured recursive resolver returned an authenticated answer (AD=1)."
    else:
        state = "unverified"
        message = "The resolver response was not authenticated (AD=0)."
    return {"state": state, "authenticated": authenticated, "resolver": resolver_ip, "message": message}
