import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, User
from app.models.mail import DistributionGroup, DistributionGroupMember

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["mailboxes"])


def _audit(db: Session, tenant_id: UUID, current: User, action: str, resource_id: str, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action=action,
            resource_type="distribution_group",
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _group(db: Session, tenant_id: UUID, group_id: UUID) -> DistributionGroup:
    group = db.scalar(
        select(DistributionGroup).where(
            DistributionGroup.id == group_id,
            DistributionGroup.tenant_id == tenant_id,
        )
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("/groups/{group_id}/members")
def list_group_members(
    tenant_id: UUID,
    group_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    group = _group(db, tenant_id, group_id)
    members = db.scalars(
        select(DistributionGroupMember)
        .where(DistributionGroupMember.group_id == group.id)
        .order_by(DistributionGroupMember.destination_address)
    ).all()
    return {
        "group_id": str(group.id),
        "items": [
            {"id": str(member.id), "destination_address": member.destination_address}
            for member in members
        ],
        "total": len(members),
    }


@router.delete("/groups/{group_id}/members/{member_id}", status_code=204)
def remove_group_member(
    tenant_id: UUID,
    group_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    group = _group(db, tenant_id, group_id)
    member = db.scalar(
        select(DistributionGroupMember).where(
            DistributionGroupMember.id == member_id,
            DistributionGroupMember.group_id == group.id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="Group member not found")

    destination = member.destination_address
    _audit(db, tenant_id, current, "group.member_remove", str(group.id), {"destination": destination})
    db.delete(member)
    db.commit()
    return Response(status_code=204)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    tenant_id: UUID,
    group_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    group = _group(db, tenant_id, group_id)
    _audit(db, tenant_id, current, "group.delete", str(group.id), {"address": group.address})
    db.delete(group)
    db.commit()
    return Response(status_code=204)
