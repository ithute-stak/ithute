from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import current_claims
from .db import SessionLocal
from .enterprise_models import AuditEvent
from .fleet import _profile, _require_admin, _require_branch
from .models import Profile, ProfileBranchAccess

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

ALLOWED_BRANCH_ROLES = {"viewer", "manager", "fleet_manager"}


class BranchAccessUpsert(BaseModel):
    profile_id: uuid.UUID
    role: str = Field(pattern=r"^(viewer|manager|fleet_manager)$")


def _audit(db, *, actor_id: uuid.UUID, branch_id: uuid.UUID, action: str, target_profile_id: uuid.UUID, detail: dict[str, Any]) -> None:
    db.add(
        AuditEvent(
            branch_id=branch_id,
            actor_profile_id=actor_id,
            action=action,
            entity_type="profile_branch_access",
            entity_id=str(target_profile_id),
            detail_json=json.dumps(detail, ensure_ascii=False, default=str),
        )
    )


@router.get("/profiles")
def list_profiles(claims: dict = Depends(current_claims)) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        actor = _profile(db, claims)
        _require_admin(actor)
        rows = list(db.scalars(select(Profile).order_by(Profile.email_snapshot, Profile.created_at)))
        return [
            {
                "id": str(row.id),
                "auth_user_id": str(row.auth_user_id),
                "email": row.email_snapshot,
                "role": row.role,
                "created_at": row.created_at,
            }
            for row in rows
        ]


@router.get("/branch-access")
def list_branch_access(
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        actor = _profile(db, claims)
        _require_admin(actor)
        _require_branch(db, actor, branch_id)
        rows = db.execute(
            select(ProfileBranchAccess, Profile)
            .join(Profile, Profile.id == ProfileBranchAccess.profile_id)
            .where(ProfileBranchAccess.branch_id == branch_id)
            .order_by(Profile.email_snapshot)
        ).all()
        return [
            {
                "id": str(access.id),
                "profile_id": str(profile.id),
                "email": profile.email_snapshot,
                "global_role": profile.role,
                "branch_role": access.role,
            }
            for access, profile in rows
        ]


@router.put("/branch-access")
def upsert_branch_access(
    payload: BranchAccessUpsert,
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> dict[str, Any]:
    with SessionLocal() as db:
        actor = _profile(db, claims)
        _require_admin(actor)
        _require_branch(db, actor, branch_id, write=True)
        target = db.get(Profile, payload.profile_id)
        if target is None:
            raise HTTPException(status_code=404, detail="profile not found")
        if target.id == actor.id and target.role == "admin":
            raise HTTPException(status_code=409, detail="global administrators do not require branch membership")

        row = db.scalar(
            select(ProfileBranchAccess).where(
                ProfileBranchAccess.profile_id == target.id,
                ProfileBranchAccess.branch_id == branch_id,
            )
        )
        previous = row.role if row else None
        if row is None:
            row = ProfileBranchAccess(profile_id=target.id, branch_id=branch_id, role=payload.role)
            db.add(row)
        else:
            row.role = payload.role
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="branch access already exists") from None
        _audit(
            db,
            actor_id=actor.id,
            branch_id=branch_id,
            action="governance.branch_access.updated",
            target_profile_id=target.id,
            detail={"previous_role": previous, "role": payload.role},
        )
        db.commit()
        db.refresh(row)
        return {"id": str(row.id), "profile_id": str(target.id), "branch_id": str(branch_id), "role": row.role}


@router.delete("/branch-access/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_branch_access(
    profile_id: uuid.UUID,
    branch_id: uuid.UUID = Query(...),
    claims: dict = Depends(current_claims),
) -> None:
    with SessionLocal() as db:
        actor = _profile(db, claims)
        _require_admin(actor)
        _require_branch(db, actor, branch_id, write=True)
        row = db.scalar(
            select(ProfileBranchAccess).where(
                ProfileBranchAccess.profile_id == profile_id,
                ProfileBranchAccess.branch_id == branch_id,
            )
        )
        if row is None:
            raise HTTPException(status_code=404, detail="branch access not found")
        previous = row.role
        db.delete(row)
        _audit(
            db,
            actor_id=actor.id,
            branch_id=branch_id,
            action="governance.branch_access.revoked",
            target_profile_id=profile_id,
            detail={"previous_role": previous},
        )
        db.commit()
