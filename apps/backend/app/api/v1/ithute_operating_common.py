from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner
from app.db.session import get_db
from app.models import (
    BackupStatus,
    DeploymentStatus,
    IthuteDeveloperClient,
    IthutePlatformEvent,
    IthutePlatformNotification,
    IthuteProduct,
    IthuteProductBackup,
    IthuteProductCommand,
    IthuteProductDeployment,
    IthuteProductHeartbeat,
    IthuteSecretReference,
    IthuteSecurityEvent,
    IthuteSubscriptionGrant,
    IthuteSupportContext,
    IthuteWebhookSubscription,
    PlatformEventStatus,
    ProductOperationalStatus,
    SecuritySeverity,
    SubscriptionGrantStatus,
    User,
)
from app.services.ithute_operating import (
    ensure_default_products,
    product_snapshot,
    utcnow,
    verify_platform_service_token,
)


router = APIRouter(prefix="/platform/ithute", tags=["ithute-operating-platform"])


class HeartbeatIn(BaseModel):
    product_id: str = Field(min_length=2, max_length=80)
    status: ProductOperationalStatus
    version: str | None = Field(default=None, max_length=80)
    database_status: str = Field(default="unknown", max_length=40)
    auth_status: str = Field(default="unknown", max_length=40)
    push_status: str = Field(default="unknown", max_length=40)
    realtime_status: str = Field(default="unknown", max_length=40)
    containers: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = Field(default=None, max_length=4000)


class EventIn(BaseModel):
    product_id: str = Field(min_length=2, max_length=80)
    source_event_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,159}$")
    subject: str | None = Field(default=None, max_length=255)
    tenant_ref: str | None = Field(default=None, max_length=255)
    trace_id: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class NotificationIn(BaseModel):
    product_id: str = Field(min_length=2, max_length=80)
    recipient_sub: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=8000)
    category: str = Field(default="general", max_length=100)
    action_url: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubscriptionGrantIn(BaseModel):
    subject_type: str = Field(pattern=r"^(user|organization|tenant)$")
    subject_id: str = Field(min_length=1, max_length=255)
    product_id: str = Field(min_length=2, max_length=80)
    plan: str = Field(default="demo", min_length=1, max_length=100)
    status: SubscriptionGrantStatus = SubscriptionGrantStatus.demo
    features: dict[str, Any] = Field(default_factory=dict)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CommandIn(BaseModel):
    command_type: str = Field(pattern=r"^(maintenance.enable|maintenance.disable|deploy|rollback|backup|restore|healthcheck|migrate)$")
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandUpdate(BaseModel):
    status: str = Field(pattern=r"^(running|succeeded|failed|cancelled)$")
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=8000)


class DeploymentIn(BaseModel):
    product_id: str = Field(min_length=2, max_length=80)
    version: str | None = Field(default=None, max_length=120)
    source_sha: str | None = Field(default=None, max_length=64)
    environment: str = Field(default="production", max_length=50)
    target: str | None = Field(default=None, max_length=255)
    status: DeploymentStatus
    backup_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=8000)
    finished_at: datetime | None = None


class BackupIn(BaseModel):
    product_id: str = Field(min_length=2, max_length=80)
    kind: str = Field(default="database", max_length=80)
    status: BackupStatus
    storage_uri: str | None = Field(default=None, max_length=1024)
    checksum: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    restore_verified: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    verified_at: datetime | None = None
    expires_at: datetime | None = None


class SupportContextIn(BaseModel):
    support_ticket_id: uuid.UUID
    product_id: str | None = Field(default=None, max_length=80)
    organization_ref: str | None = Field(default=None, max_length=255)
    user_ref: str | None = Field(default=None, max_length=255)
    trace_id: str | None = Field(default=None, max_length=128)
    deployment_id: uuid.UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SecurityEventIn(BaseModel):
    product_id: str | None = Field(default=None, max_length=80)
    severity: SecuritySeverity = SecuritySeverity.info
    event_type: str = Field(min_length=2, max_length=160)
    actor_ref: str | None = Field(default=None, max_length=255)
    subject_ref: str | None = Field(default=None, max_length=255)
    source_ip: str | None = Field(default=None, max_length=64)
    details: dict[str, Any] = Field(default_factory=dict)


class SecretReferenceIn(BaseModel):
    product_id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    provider: str = Field(default="docker_secret", max_length=80)
    reference: str = Field(min_length=1, max_length=512)
    version: str | None = Field(default=None, max_length=80)
    rotation_due_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeveloperClientIn(BaseModel):
    client_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,159}$")
    name: str = Field(min_length=2, max_length=200)
    owner_ref: str = Field(min_length=1, max_length=255)
    allowed_products: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class WebhookIn(BaseModel):
    developer_client_id: uuid.UUID
    product_id: str | None = Field(default=None, max_length=80)
    event_pattern: str = Field(min_length=2, max_length=160)
    target_url: HttpUrl
    secret_reference_id: uuid.UUID | None = None


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Ithute platform service token required")
    return authorization.split(" ", 1)[1].strip()


def _service_claims(
    authorization: str | None,
    *,
    scope: str,
    product_id: str | None,
) -> dict[str, Any]:
    try:
        return verify_platform_service_token(
            _bearer_token(authorization),
            required_scope=scope,
            product_id=product_id,
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Ithute platform service token") from exc


def _subject_id(current: User) -> str:
    return str(current.auth_user_id or current.id)


def _product_or_404(db: Session, product_id: str) -> IthuteProduct:
    ensure_default_products(db)
    product = db.get(IthuteProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _serialize_event(item: IthutePlatformEvent) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "product_id": item.product_id,
        "source_event_id": item.source_event_id,
        "event_type": item.event_type,
        "subject": item.subject,
        "tenant_ref": item.tenant_ref,
        "trace_id": item.trace_id,
        "payload": item.payload_json,
        "status": item.status.value,
        "occurred_at": item.occurred_at.isoformat(),
        "created_at": item.created_at.isoformat(),
    }
