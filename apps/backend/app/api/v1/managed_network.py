from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.models import HostingNode, HostingNodeAgent, InfrastructureNetworkGrant, InfrastructureServer, InfrastructureWireGuardPeer, User
from app.services.managed_network import allocate_peer, enrollment_response, peer_list

router = APIRouter(tags=["managed-private-network"])


class NetworkEnroll(BaseModel):
    public_key: str = Field(min_length=40, max_length=128)


class NetworkGrantCreate(BaseModel):
    source_server_id: UUID
    target_server_id: UUID
    protocol: str = Field(pattern=r"^(tcp|udp)$")
    port: int = Field(ge=1, le=65535)
    service: str = Field(min_length=1, max_length=80)


def _hosting_agent(db: Session, token: str | None) -> tuple[HostingNodeAgent, HostingNode]:
    raw = (token or "").strip()
    if not raw.startswith("ith_host_"):
        raise HTTPException(status_code=401, detail="Hosting node agent credential required")
    agent = db.scalar(select(HostingNodeAgent).where(HostingNodeAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid hosting node agent credential")
    node = db.get(HostingNode, agent.node_id)
    if node is None or node.status == "offline":
        raise HTTPException(status_code=403, detail="Hosting node is unavailable")
    return agent, node


@router.post("/hosting/agent/network/enroll")
def enroll_managed_network(
    payload: NetworkEnroll,
    x_ithute_hosting_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent, node = _hosting_agent(db, x_ithute_hosting_agent)
    server = db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node.id))
    if server is None:
        raise HTTPException(status_code=409, detail="Hosting node must be linked to an infrastructure server before network enrollment")
    peer = allocate_peer(db, server, payload.public_key)
    agent.origin_bind_ip = peer.assigned_ipv4
    db.commit()
    return enrollment_response(peer)


def _grant_out(db: Session, row: InfrastructureNetworkGrant) -> dict:
    source = db.get(InfrastructureServer, row.source_server_id)
    target = db.get(InfrastructureServer, row.target_server_id)
    source_peer = db.scalar(select(InfrastructureWireGuardPeer).where(InfrastructureWireGuardPeer.server_id == row.source_server_id))
    target_peer = db.scalar(select(InfrastructureWireGuardPeer).where(InfrastructureWireGuardPeer.server_id == row.target_server_id))
    return {
        "id": str(row.id),
        "source_server_id": str(row.source_server_id),
        "source_name": source.name if source else None,
        "source_ipv4": source_peer.assigned_ipv4 if source_peer and source_peer.status == "active" else None,
        "target_server_id": str(row.target_server_id),
        "target_name": target.name if target else None,
        "target_ipv4": target_peer.assigned_ipv4 if target_peer and target_peer.status == "active" else None,
        "protocol": row.protocol,
        "port": row.port,
        "service": row.service,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/platform/infrastructure/private-network/grants")
def list_private_network_grants(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(
        select(InfrastructureNetworkGrant)
        .order_by(InfrastructureNetworkGrant.created_at.asc())
    ).all()
    return {"items": [_grant_out(db, row) for row in rows]}


@router.post("/platform/infrastructure/private-network/grants", status_code=201)
def create_private_network_grant(
    payload: NetworkGrantCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if payload.source_server_id == payload.target_server_id:
        raise HTTPException(status_code=422, detail="Source and target servers must be different")
    source = db.get(InfrastructureServer, payload.source_server_id)
    target = db.get(InfrastructureServer, payload.target_server_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Source or target infrastructure server not found")
    if source.status != "active" or target.status != "active":
        raise HTTPException(status_code=409, detail="Both servers must be active")
    for server_id, label in ((source.id, "source"), (target.id, "target")):
        peer = db.scalar(
            select(InfrastructureWireGuardPeer).where(
                InfrastructureWireGuardPeer.server_id == server_id,
                InfrastructureWireGuardPeer.status == "active",
            )
        )
        if peer is None:
            raise HTTPException(status_code=409, detail=f"The {label} server is not enrolled in the managed private network")

    existing = db.scalar(
        select(InfrastructureNetworkGrant).where(
            InfrastructureNetworkGrant.source_server_id == source.id,
            InfrastructureNetworkGrant.target_server_id == target.id,
            InfrastructureNetworkGrant.protocol == payload.protocol,
            InfrastructureNetworkGrant.port == payload.port,
        )
    )
    if existing is not None:
        existing.service = payload.service.strip()
        existing.enabled = True
        db.commit()
        db.refresh(existing)
        return _grant_out(db, existing)

    row = InfrastructureNetworkGrant(
        source_server_id=source.id,
        target_server_id=target.id,
        protocol=payload.protocol,
        port=payload.port,
        service=payload.service.strip(),
        enabled=True,
        created_by_user_id=current.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _grant_out(db, row)


@router.delete("/platform/infrastructure/private-network/grants/{grant_id}", status_code=204)
def delete_private_network_grant(
    grant_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = db.get(InfrastructureNetworkGrant, grant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Private network grant not found")
    db.delete(row)
    db.commit()


@router.get("/platform/infrastructure/private-network")
def private_network_status(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(select(InfrastructureWireGuardPeer).order_by(InfrastructureWireGuardPeer.assigned_ipv4.asc())).all()
    edge_public_key = os.getenv("ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY", "").strip()
    edge_endpoint = os.getenv("ITHUTE_WIREGUARD_EDGE_ENDPOINT", "").strip()
    reconciler_configured = bool(os.getenv("ITHUTE_WIREGUARD_RECONCILER_TOKEN", "").strip())
    base = peer_list(db)
    return {
        **base,
        "configured": bool(edge_public_key and edge_endpoint and reconciler_configured),
        "edge_public_key": edge_public_key or None,
        "edge_endpoint": edge_endpoint or None,
        "reconciler_configured": reconciler_configured,
        "policy_mode": "full_mesh",
        "peer_communication_default": "allow",
        "items": [
            {
                "id": str(row.id),
                "server_id": str(row.server_id),
                "public_key": row.public_key,
                "assigned_ipv4": row.assigned_ipv4,
                "status": row.status,
                "last_handshake_at": row.last_handshake_at.isoformat() if row.last_handshake_at else None,
                "rx_bytes": row.latest_rx_bytes,
                "tx_bytes": row.latest_tx_bytes,
            }
            for row in rows
        ],
    }


@router.get("/infrastructure/private-network/edge-peers")
def edge_peer_configuration(
    x_ithute_wireguard_reconciler: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("ITHUTE_WIREGUARD_RECONCILER_TOKEN", "").strip()
    supplied = (x_ithute_wireguard_reconciler or "").strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Private-network reconciler credential required")
    config = peer_list(db)
    config["policy_mode"] = "full_mesh"
    config["peer_communication_default"] = "allow"
    return config
