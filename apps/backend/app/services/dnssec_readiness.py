"""Read-only DNSSEC activation readiness classification.

This module never modifies authoritative or registrar records. Unknown observations
are not interpreted as a safe absence of parent DS records.
"""
from __future__ import annotations


def activation_readiness(*, signing: bool, delegation: dict, registrar_configured: bool,
                         recommended_ds: str | None, parent_contains_recommended: bool,
                         registrar_error: str | None = None, available_ds: bool = False, registrar_algorithms: list[int] | None = None) -> dict:
    def step(key: str, label: str, state: str, detail: str) -> dict:
        return {"key": key, "label": label, "state": state, "detail": detail}

    delegation_error = delegation.get("delegation_error")
    parent_error = delegation.get("parent_ds_error")
    parent_records = delegation.get("parent_ds") or []
    parent_known = (not parent_error or parent_error in {"NoAnswer", "NXDOMAIN"}) or bool(parent_records)
    parent_lookup_failed = bool(parent_error and parent_error not in {"NoAnswer", "NXDOMAIN"} and not parent_records)
    steps = [
        step("signing", "Authoritative DNSSEC signing",
             "complete" if signing else "pending",
             "Zone signing is enabled." if signing else "Enable DNSSEC signing in PowerDNS."),
        step("delegation", "Public nameserver delegation",
             "blocked" if delegation_error else ("complete" if delegation.get("ready") else "pending"),
             "Resolver lookup failed; verify public delegation." if delegation_error else
             ("Platform delegation and nameserver addresses are ready." if delegation.get("ready") else "Delegation or nameserver reachability needs attention.")),
        step("registrar", "Registrar automation connection",
             "complete" if registrar_configured and not registrar_error else ("blocked" if registrar_error else "pending"),
             "OpenSRS connection is available." if registrar_configured and not registrar_error else
             (f"OpenSRS returned an error: {registrar_error}" if registrar_error else "OpenSRS credentials are not configured; use manual DS publication.")),
        step("ds", "Compatible DS record",
             "complete" if recommended_ds else "pending",
             "A registrar-compatible DS record is available." if recommended_ds else
             ("PowerDNS has DS records, but their key algorithms are not supported by OpenSRS; prepare a compatible KSK without removing existing keys." if available_ds else "No supported DS record found; verify signing keys and generate a compatible KSK.")),
        step("parent", "Parent registry DS verification",
             "blocked" if parent_lookup_failed else ("complete" if recommended_ds and parent_contains_recommended else "pending"),
             "Public parent DS lookup failed; do not assume that parent records are absent." if parent_lookup_failed else
             ("The expected DS record is visible in public DNS." if recommended_ds and parent_contains_recommended else "Expected DS record not yet verified at the parent.")),
    ]
    # Registrar automation is optional when DS can be published manually.
    chain_ready = bool(signing and delegation.get("ready") and not delegation_error
                       and recommended_ds and parent_known and parent_contains_recommended)
    return {"ready": chain_ready, "parent_lookup_state": "error" if parent_lookup_failed else ("present" if parent_records else "not_observed"),
            "registrar_supported_algorithms": registrar_algorithms or [], "state": "verified" if chain_ready else
            ("blocked" if any(s["state"] == "blocked" for s in steps) else "pending"),
            "steps": steps, "read_only": True}
