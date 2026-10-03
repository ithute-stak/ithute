from __future__ import annotations


def audit_security_severity(action: str) -> str | None:
    value = (action or "").strip().lower()

    critical = (
        "failover.complete",
        "security.approval.approve",
        "security.approval.reject",
        "tenant.delete",
        "domain.transfer",
        "dnssec.disable",
        "backup.delete",
    )
    if any(item in value for item in critical):
        return "critical"

    high = (
        "password",
        "mfa",
        "api_key",
        "smtp_credential",
        "agent-token",
        "token.rotate",
        "auth.ithute.unlink",
        "mail_node.failover",
        "security.approval.request",
        "role",
        "membership",
    )
    if any(item in value for item in high):
        return "high"

    medium = (
        "login",
        "session",
        "revoke",
        "dkim",
        "dmarc",
        "dns.",
        "domain.",
        "mail_node",
        "backup",
        "security",
    )
    if any(item in value for item in medium):
        return "medium"

    return None
