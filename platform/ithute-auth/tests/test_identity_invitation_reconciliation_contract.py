from pathlib import Path


ROOT = Path(__file__).parents[1]
RECONCILIATION = ROOT / "app" / "identity_invitation_reconciliation.py"
SERVER = ROOT / "app" / "server.py"


def test_reconciliation_lookup_is_source_scoped_consumed_and_managed() -> None:
    source = RECONCILIATION.read_text(encoding="utf-8")
    assert 'prefix="/v1/platform/identity-invitations"' in source
    assert '@router.get("/activated-sub/{user_id}"' in source
    assert 'Depends(require_managed_service_scope("identity.invite"))' in source
    assert "IdentityInvitation.source_client_id == context.client_id" in source
    assert "IdentityInvitation.user_id == user_id" in source
    assert "IdentityInvitation.consumed_at.is_not(None)" in source
    assert 'IdentityInvitation.status == "activated"' in source


def test_static_reconciliation_route_is_mounted_before_uuid_invitation_route() -> None:
    source = SERVER.read_text(encoding="utf-8")
    reconciliation = source.index("app.include_router(identity_invitation_reconciliation_router)")
    platform = source.index("app.include_router(identity_invitation_platform_router)")
    assert reconciliation < platform
