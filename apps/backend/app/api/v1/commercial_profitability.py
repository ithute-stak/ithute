from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import (
    AuditLog,
    InfrastructureCommercialProfile,
    InfrastructureServer,
    Tenant,
    TenantInfrastructureAllocation,
    User,
)
from app.services.commercial_profitability import customer_profitability, profitability_portfolio

router = APIRouter(prefix="/platform/commercial", tags=["commercial-profitability"])


class ServerCostProfilePayload(BaseModel):
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    provider_cost_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    backup_cost_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    bandwidth_cost_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    other_cost_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    total_cpu_millicores: int = Field(default=0, ge=0, le=100_000_000)
    total_memory_mb: int = Field(default=0, ge=0, le=100_000_000)
    total_storage_mb: int = Field(default=0, ge=0, le=2_000_000_000)
    included_bandwidth_gb: int = Field(default=0, ge=0, le=100_000_000)
    target_margin_bps: int = Field(default=3000, ge=0, le=10000)
    notes: str | None = Field(default=None, max_length=4000)


class AllocationPayload(BaseModel):
    allocation_weight: int = Field(default=1, ge=1, le=1_000_000)
    cpu_millicores: int = Field(default=0, ge=0, le=100_000_000)
    memory_mb: int = Field(default=0, ge=0, le=100_000_000)
    storage_mb: int = Field(default=0, ge=0, le=2_000_000_000)
    bandwidth_gb: int = Field(default=0, ge=0, le=100_000_000)
    active: bool = True
    source: str = Field(default="manual", pattern=r"^(manual|placement|import)$")
    notes: str | None = Field(default=None, max_length=4000)


def _audit(db: Session, current: User, action: str, resource_type: str, resource_id: str, metadata: dict) -> None:
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def _profile_out(profile: InfrastructureCommercialProfile, server: InfrastructureServer) -> dict:
    return {
        "server_id": str(server.id),
        "server_name": server.name,
        "hostname": server.hostname,
        "provider": server.provider,
        "region": server.region,
        "currency": profile.currency,
        "provider_cost_minor": profile.provider_cost_minor,
        "backup_cost_minor": profile.backup_cost_minor,
        "bandwidth_cost_minor": profile.bandwidth_cost_minor,
        "other_cost_minor": profile.other_cost_minor,
        "monthly_cost_minor": (
            profile.provider_cost_minor
            + profile.backup_cost_minor
            + profile.bandwidth_cost_minor
            + profile.other_cost_minor
        ),
        "total_cpu_millicores": profile.total_cpu_millicores,
        "total_memory_mb": profile.total_memory_mb,
        "total_storage_mb": profile.total_storage_mb,
        "included_bandwidth_gb": profile.included_bandwidth_gb,
        "target_margin_bps": profile.target_margin_bps,
        "notes": profile.notes,
    }


def _allocation_out(row: TenantInfrastructureAllocation, tenant: Tenant, server: InfrastructureServer) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "server_id": str(server.id),
        "server_name": server.name,
        "hostname": server.hostname,
        "allocation_weight": row.allocation_weight,
        "cpu_millicores": row.cpu_millicores,
        "memory_mb": row.memory_mb,
        "storage_mb": row.storage_mb,
        "bandwidth_gb": row.bandwidth_gb,
        "active": row.active,
        "source": row.source,
        "notes": row.notes,
    }


@router.get("/profitability")
def portfolio(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    return profitability_portfolio(db)


@router.get("/customers/{tenant_id}")
def customer_environment(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        return customer_profitability(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/server-costs")
def list_server_costs(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    servers = db.scalars(select(InfrastructureServer).order_by(InfrastructureServer.name)).all()
    items = []
    for server in servers:
        profile = db.scalar(
            select(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server.id)
        )
        if profile is None:
            items.append({
                "server_id": str(server.id),
                "server_name": server.name,
                "hostname": server.hostname,
                "provider": server.provider,
                "region": server.region,
                "configured": False,
            })
        else:
            items.append({"configured": True, **_profile_out(profile, server)})
    return {"items": items}


@router.put("/servers/{server_id}/cost-profile")
def upsert_server_cost_profile(
    server_id: UUID,
    payload: ServerCostProfilePayload,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    server = db.get(InfrastructureServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")
    currency = payload.currency.strip().upper()
    if currency != "LSL":
        raise HTTPException(status_code=422, detail="Infrastructure commercial accounting currently uses LSL")

    profile = db.scalar(
        select(InfrastructureCommercialProfile).where(InfrastructureCommercialProfile.server_id == server_id)
    )
    created = profile is None
    if profile is None:
        profile = InfrastructureCommercialProfile(
            server_id=server_id,
            created_by_user_id=current.id,
            updated_by_user_id=current.id,
        )
        db.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    profile.currency = currency
    profile.updated_by_user_id = current.id
    db.flush()
    _audit(
        db,
        current,
        "commercial.server_cost.create" if created else "commercial.server_cost.update",
        "infrastructure_server",
        str(server_id),
        payload.model_dump(),
    )
    db.commit()
    db.refresh(profile)
    return _profile_out(profile, server)


@router.get("/allocations")
def list_allocations(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(
        select(TenantInfrastructureAllocation).order_by(
            TenantInfrastructureAllocation.tenant_id,
            TenantInfrastructureAllocation.server_id,
        )
    ).all()
    items = []
    for row in rows:
        tenant = db.get(Tenant, row.tenant_id)
        server = db.get(InfrastructureServer, row.server_id)
        if tenant is not None and server is not None:
            items.append(_allocation_out(row, tenant, server))
    return {"items": items}


@router.put("/customers/{tenant_id}/servers/{server_id}/allocation")
def upsert_allocation(
    tenant_id: UUID,
    server_id: UUID,
    payload: AllocationPayload,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    tenant = db.get(Tenant, tenant_id)
    server = db.get(InfrastructureServer, server_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")

    row = db.scalar(
        select(TenantInfrastructureAllocation).where(
            TenantInfrastructureAllocation.tenant_id == tenant_id,
            TenantInfrastructureAllocation.server_id == server_id,
        )
    )
    created = row is None
    if row is None:
        row = TenantInfrastructureAllocation(
            tenant_id=tenant_id,
            server_id=server_id,
            created_by_user_id=current.id,
            updated_by_user_id=current.id,
        )
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by_user_id = current.id
    db.flush()
    _audit(
        db,
        current,
        "commercial.allocation.create" if created else "commercial.allocation.update",
        "tenant_infrastructure_allocation",
        str(row.id),
        {"tenant_id": str(tenant_id), "server_id": str(server_id), **payload.model_dump()},
    )
    db.commit()
    db.refresh(row)
    return _allocation_out(row, tenant, server)
