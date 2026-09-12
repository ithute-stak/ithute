from app.models import MembershipRole

ROLE_PERMISSIONS: dict[MembershipRole, frozenset[str]] = {
    MembershipRole.tenant_admin: frozenset({
        "identity.manage",
        "dns.read", "dns.manage",
        "mail.read", "mail.manage",
        "audit.read",
        "api_keys.manage",
        "billing.read", "billing.manage",
    }),
    MembershipRole.dns_admin: frozenset({"dns.read", "dns.manage", "audit.read"}),
    MembershipRole.mail_admin: frozenset({"mail.read", "mail.manage", "audit.read"}),
    MembershipRole.auditor: frozenset({"dns.read", "mail.read", "audit.read", "billing.read"}),
    MembershipRole.member: frozenset({"profile.read"}),
}


def has_permission(role: MembershipRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
