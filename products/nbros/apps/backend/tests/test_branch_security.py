import uuid

import pytest
from fastapi import HTTPException

from app.fleet import _require_branch
from app.models import Profile, ProfileBranchAccess


def test_branch_access_isolation_and_roles(db, branch):
    viewer = Profile(auth_user_id=uuid.uuid4(), email_snapshot="viewer@example.com", role="user")
    db.add(viewer)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        _require_branch(db, viewer, branch.id)
    assert exc.value.status_code == 403

    membership = ProfileBranchAccess(profile_id=viewer.id, branch_id=branch.id, role="viewer")
    db.add(membership)
    db.commit()

    assert _require_branch(db, viewer, branch.id).id == branch.id

    with pytest.raises(HTTPException) as exc:
        _require_branch(db, viewer, branch.id, write=True)
    assert exc.value.status_code == 403

    membership.role = "fleet_manager"
    db.commit()
    assert _require_branch(db, viewer, branch.id, write=True).id == branch.id


def test_global_fleet_admin_can_access_enabled_branch_without_membership(db, branch):
    admin = Profile(auth_user_id=uuid.uuid4(), email_snapshot="admin@example.com", role="fleet_admin")
    db.add(admin)
    db.commit()
    assert _require_branch(db, admin, branch.id, write=True).id == branch.id
