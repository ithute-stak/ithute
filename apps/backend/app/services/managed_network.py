from __future__ import annotations

import ipaddress
import os
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InfrastructureServer, InfrastructureWireGuardPeer

_WG_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")


def _mesh_network() -> ipaddress.IPv4Network:
    raw = os.getenv("ITHUTE_WIREGUARD_SUBNET", "10.70.0.0/24").strip()
    try:
        network = ipaddress.ip_network(raw, strict=False)
    except ValueError as exc:
        raise RuntimeError("ITHUTE_WIREGUARD_SUBNET is invalid") from exc
    if not isinstance(network, ipaddress.IPv4Network) or not network.is_private or network.prefixlen < 20 or network.prefixlen > 29:
        raise RuntimeError("ITHUTE_WIREGUARD_SUBNET must be a private IPv4 /20 to /29 network")
    return network


def edge_address() -> str:
    network = _mesh_network()
    configured = os.getenv("ITHUTE_WIREGUARD_EDGE_ADDRESS", "").strip()
    if configured:
        address = ipaddress.ip_address(configured)
        if not isinstance(address, ipaddress.IPv4Address) or address not in network or address in {network.network_address, network.broadcast_address}:
            raise RuntimeError("ITHUTE_WIREGUARD_EDGE_ADDRESS must be a usable host address inside ITHUTE_WIREGUARD_SUBNET")
        return str(address)
    return str(next(network.hosts()))


def _edge_public_key() -> str:
    value = os.getenv("ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY", "").strip()
    if not _WG_KEY_RE.fullmatch(value):
        raise HTTPException(status_code=503, detail="Managed private networking is not configured on the Ithute edge")
    return value


def _edge_endpoint() -> str:
    value = os.getenv("ITHUTE_WIREGUARD_EDGE_ENDPOINT", "").strip()
    if not value or len(value) > 300 or "\r" in value or "\n" in value:
        raise HTTPException(status_code=503, detail="Managed private networking edge endpoint is not configured")
    match = re.fullmatch(r"([A-Za-z0-9.-]+):(\d{1,5})", value)
    if not match:
        raise HTTPException(status_code=503, detail="Managed private networking edge endpoint must be host:port")
    port = int(match.group(2))
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=503, detail="Managed private networking edge endpoint port is invalid")
    return value


def allocate_peer(db: Session, server: InfrastructureServer, public_key: str) -> InfrastructureWireGuardPeer:
    key = public_key.strip()
    if not _WG_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=422, detail="Invalid WireGuard public key")

    existing_by_key = db.scalar(select(InfrastructureWireGuardPeer).where(InfrastructureWireGuardPeer.public_key == key))
    if existing_by_key is not None and existing_by_key.server_id != server.id:
        raise HTTPException(status_code=409, detail="This WireGuard public key is already assigned to another server")

    peer = db.scalar(
        select(InfrastructureWireGuardPeer)
        .where(InfrastructureWireGuardPeer.server_id == server.id)
        .with_for_update()
    )
    if peer is not None:
        peer.public_key = key
        peer.status = "active"
        return peer

    network = _mesh_network()
    reserved = {edge_address()}
    used = set(db.scalars(select(InfrastructureWireGuardPeer.assigned_ipv4)).all())
    candidate = None
    for address in network.hosts():
        value = str(address)
        if value in reserved or value in used:
            continue
        candidate = value
        break
    if candidate is None:
        raise HTTPException(status_code=409, detail="Managed private network address pool is exhausted")

    peer = InfrastructureWireGuardPeer(
        server_id=server.id,
        public_key=key,
        assigned_ipv4=candidate,
        status="active",
    )
    db.add(peer)
    db.flush()
    return peer


def enrollment_response(peer: InfrastructureWireGuardPeer) -> dict:
    network = _mesh_network()
    return {
        "interface": "ithute0",
        "address": f"{peer.assigned_ipv4}/32",
        "assigned_ipv4": peer.assigned_ipv4,
        "edge_public_key": _edge_public_key(),
        "edge_endpoint": _edge_endpoint(),
        "allowed_ips": f"{network.network_address}/{network.prefixlen}",
        "edge_source_cidrs": f"{edge_address()}/32",
        "persistent_keepalive": 25,
    }


def peer_list(db: Session) -> dict:
    network = _mesh_network()
    rows = db.scalars(
        select(InfrastructureWireGuardPeer)
        .where(InfrastructureWireGuardPeer.status == "active")
        .order_by(InfrastructureWireGuardPeer.assigned_ipv4.asc())
    ).all()
    return {
        "interface": "ithute0",
        "subnet": str(network),
        "edge_address": f"{edge_address()}/{network.prefixlen}",
        "listen_port": int(os.getenv("ITHUTE_WIREGUARD_LISTEN_PORT", "51820")),
        "peers": [
            {
                "server_id": str(row.server_id),
                "public_key": row.public_key,
                "allowed_ip": f"{row.assigned_ipv4}/32",
            }
            for row in rows
        ],
    }


def update_peer_telemetry(
    db: Session,
    server_id,
    *,
    latest_handshake_at: datetime | None,
    rx_bytes: int | None,
    tx_bytes: int | None,
) -> None:
    peer = db.scalar(select(InfrastructureWireGuardPeer).where(InfrastructureWireGuardPeer.server_id == server_id))
    if peer is None:
        return
    peer.last_handshake_at = latest_handshake_at
    peer.latest_rx_bytes = rx_bytes
    peer.latest_tx_bytes = tx_bytes
    peer.updated_at = datetime.now(timezone.utc)
