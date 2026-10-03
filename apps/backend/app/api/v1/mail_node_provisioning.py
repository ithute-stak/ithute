from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.config import settings
from app.core.security import hash_token
from app.db.session import get_db
from app.models import AuditLog, MailNode, MailNodeAgent, Tenant, User
from app.services.mail_node_provisioner import MailNodeProvisionerError, provision_mail_node, provisioner_configured

router = APIRouter(tags=["mail-node-provisioning"])


class ProvisionMailNodeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    region: str = Field(default="lesotho", min_length=2, max_length=80)
    tenant_id: UUID | None = None
    storage_gb: int = Field(ge=20, le=65536)
    memory_mb: int = Field(default=4096, ge=2048, le=262144)
    cpu_cores: int = Field(default=2, ge=1, le=128)
    hostname: str = Field(min_length=3, max_length=253)


@router.get("/platform/mail-node-provisioner")
def mail_node_provisioner_status(
    current: User = Depends(require_platform_owner),
):
    return {"configured": provisioner_configured()}


@router.post("/platform/mail-nodes/provision", status_code=202)
def provision_node(
    payload: ProvisionMailNodeRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if not provisioner_configured():
        raise HTTPException(status_code=409, detail="Mail node provisioner is not configured")
    if payload.tenant_id is not None and db.get(Tenant, payload.tenant_id) is None:
        raise HTTPException(status_code=404, detail="Dedicated tenant not found")

    node = MailNode(
        name=payload.name.strip(),
        role="combined",
        region=payload.region.strip().lower(),
        hostname=payload.hostname.strip().lower().rstrip("."),
        tenant_id=payload.tenant_id,
        storage_path="/srv/ithute-mail/data/mail-data",
        capabilities_json='["mail","storage"]',
        status="provisioning",
    )
    db.add(node)
    db.flush()

    raw_agent_token = "ith_mail_" + secrets.token_urlsafe(36)
    agent = MailNodeAgent(
        node_id=node.id,
        token_hash=hash_token(raw_agent_token),
        token_hint=raw_agent_token[:18],
        rotated_at=datetime.now(timezone.utc),
        rotated_by_user_id=current.id,
    )
    db.add(agent)
    db.commit()

    request_body = {
        "request_version": 1,
        "node_id": str(node.id),
        "name": node.name,
        "region": node.region,
        "tenant_id": str(node.tenant_id) if node.tenant_id else None,
        "hostname": node.hostname,
        "resources": {
            "storage_gb": payload.storage_gb,
            "memory_mb": payload.memory_mb,
            "cpu_cores": payload.cpu_cores,
        },
        "bootstrap": {
            "api_url": settings.mail_node_control_plane_url,
            "agent_token": raw_agent_token,
            "profile": "ithute-mail-node-v1",
            "mail_hostname": node.hostname,
        },
    }

    try:
        result = provision_mail_node(request_body)
    except MailNodeProvisionerError as exc:
        node.status = "disabled"
        db.add(AuditLog(
            actor_user_id=current.id,
            tenant_id=node.tenant_id,
            action="mail_node.provision.failed",
            resource_type="mail_node",
            resource_id=str(node.id),
            metadata_json=json.dumps({"error": str(exc)[:1000]}),
        ))
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result["hostname"] != payload.hostname.strip().lower().rstrip("."):
        node.status = "disabled"
        db.commit()
        raise HTTPException(status_code=502, detail="Provisioner returned a hostname different from the requested mail hostname")

    node.provider = result["provider"]
    node.provider_instance_id = result["instance_id"]
    node.hostname = result["hostname"]
    node.public_ip = result["public_ip"]
    node.ssh_user = result["ssh_user"]
    node.ssh_port = result["ssh_port"]
    db.add(AuditLog(
        actor_user_id=current.id,
        tenant_id=node.tenant_id,
        action="mail_node.provision.accepted",
        resource_type="mail_node",
        resource_id=str(node.id),
        metadata_json=json.dumps({
            "provider": node.provider,
            "provider_instance_id": node.provider_instance_id,
            "storage_gb": payload.storage_gb,
        }),
    ))
    db.commit()
    db.refresh(node)
    return {
        "id": str(node.id),
        "name": node.name,
        "status": node.status,
        "provider": node.provider,
        "provider_instance_id": node.provider_instance_id,
        "hostname": node.hostname,
        "public_ip": node.public_ip,
        "message": "Provisioning accepted. The node becomes active only after its agent reports SMTP, IMAP and TLS ready.",
    }
