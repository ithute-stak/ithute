from app.core.rbac import has_permission
from app.models import MembershipRole


def test_tenant_admin_has_full_control_plane_permissions():
    assert has_permission(MembershipRole.tenant_admin, "identity.manage")
    assert has_permission(MembershipRole.tenant_admin, "dns.manage")
    assert has_permission(MembershipRole.tenant_admin, "mail.manage")
    assert has_permission(MembershipRole.tenant_admin, "audit.read")


def test_specialized_roles_are_least_privilege():
    assert has_permission(MembershipRole.dns_admin, "dns.manage")
    assert not has_permission(MembershipRole.dns_admin, "mail.manage")
    assert has_permission(MembershipRole.mail_admin, "mail.manage")
    assert not has_permission(MembershipRole.mail_admin, "dns.manage")
    assert has_permission(MembershipRole.auditor, "audit.read")
    assert not has_permission(MembershipRole.auditor, "identity.manage")
    assert not has_permission(MembershipRole.member, "audit.read")
