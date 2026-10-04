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
from app.models import HostingNode, HostingNodeAgent, InfrastructureServer, InfrastructureWireGuardPeer, User
from app.services.managed_network import allocate_peer, enrollment_response, peer_list

router = APIRouter(tags=["managed-private-network"])


class NetworkEnroll(BaseModel):
    public_key: str = Field(min_length=40, max_length=128)


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


@router.get("/platform/infrastructure/private-network")
def private_network_status(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    rows = db.scalars(select(InfrastructureWireGuardPeer).order_by(InfrastructureWireGuardPeer.assigned_ipv4.asc())).all()
    return {
        **peer_list(db),
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
    return peer_list(db)
