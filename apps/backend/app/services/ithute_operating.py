from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IthuteProduct, IthuteProductHeartbeat, ProductOperationalStatus


class PlatformServiceAuthSettings(BaseSettings):
    issuer: str = "https://auth.ithute.co.ls"
    jwks_url: str | None = None
    audience: str = "ithute-platform"
    allowed_clients: str = "mailbox-dns,loanhub,ithute-pay,ithute-tutor"

    model_config = SettingsConfigDict(
        env_prefix="ITHUTE_PLATFORM_SERVICE_AUTH_",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def resolved_issuer(self) -> str:
        return self.issuer.rstrip("/")

    @property
    def resolved_jwks_url(self) -> str:
        return self.jwks_url or f"{self.resolved_issuer}/.well-known/jwks.json"

    @property
    def allowed_client_ids(self) -> set[str]:
        return {item.strip() for item in self.allowed_clients.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_platform_service_auth_settings() -> PlatformServiceAuthSettings:
    return PlatformServiceAuthSettings()


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def verify_platform_service_token(
    token: str,
    *,
    required_scope: str,
    product_id: str | None = None,
) -> dict[str, Any]:
    cfg = get_platform_service_auth_settings()
    key = _jwks_client(cfg.resolved_jwks_url).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=cfg.resolved_issuer,
        audience=cfg.audience,
        options={"require": ["iss", "sub", "aud", "azp", "scope", "token_use", "iat", "nbf", "exp"]},
    )
    if claims.get("token_use") != "service":
        raise jwt.InvalidTokenError("platform ingest requires a service token")
    client_id = str(claims.get("azp") or "")
    if not client_id or client_id not in cfg.allowed_client_ids:
        raise jwt.InvalidTokenError("service client is not allowed to use the Ithute platform")
    if claims.get("sub") != f"service:{client_id}":
        raise jwt.InvalidTokenError("service subject does not match authorized party")
    scopes = {part for part in str(claims.get("scope") or "").split() if part}
    if required_scope not in scopes:
        raise jwt.InvalidTokenError(f"required scope missing: {required_scope}")
    if product_id is not None and client_id != product_id:
        raise jwt.InvalidTokenError("service client may only write its own product state")
    return claims


DEFAULT_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "id": "mailbox-dns",
        "name": "Ithute Mailbox",
        "category": "communications",
        "public_url": "https://panel.ithute.co.ls",
        "api_url": "https://api.ithute.co.ls/api/v1",
        "health_url": "https://api.ithute.co.ls/health/ready",
        "deployment_target": "mailbox-primary",
        "database_engine": "postgresql",
        "metadata_json": {
            "services": ["smtp", "imap", "dns", "webmail", "groupware"],
            "source_path": ".",
        },
    },
    {
        "id": "loanhub",
        "name": "LoanHub",
        "category": "financial-services",
        "public_url": "https://loanhub.co.ls",
        "api_url": "https://api.loanhub.co.ls/api/v1",
        "health_url": "https://api.loanhub.co.ls/health/ready",
        "deployment_target": "204.12.205.224",
        "database_engine": "postgresql",
        "metadata_json": {
            "services": ["backend", "frontend", "postgresql", "redis", "maintenance"],
            "repository_url": "https://github.com/ithute-stak/LoanHub",
            "data_protection": {
                "preserve_existing_volume": True,
                "require_pre_migration_backup": True,
            },
        },
    },
    {
        "id": "ithute-pay",
        "name": "Ithute Pay",
        "category": "payments",
        "public_url": "https://pay.ithute.co.ls",
        "api_url": None,
        "health_url": None,
        "deployment_target": "ithute-platform",
        "database_engine": "postgresql",
        "metadata_json": {
            "services": ["app", "postgresql", "redis"],
            "repository_url": "https://github.com/ithute-stak/ithute-pay",
        },
    },
    {
        "id": "ithute-tutor",
        "name": "Ithute Tutor",
        "category": "education",
        "public_url": "https://tutor.ithute.co.ls",
        "api_url": None,
        "health_url": None,
        "deployment_target": "ithute-platform",
        "database_engine": "postgresql",
        "metadata_json": {
            "services": ["backend", "frontend", "postgresql"],
            "repository_url": "https://github.com/ithute-stak/ithute-tutor",
        },
    },
)


def ensure_default_products(db: Session) -> list[IthuteProduct]:
    changed = False
    for item in DEFAULT_PRODUCTS:
        product = db.get(IthuteProduct, item["id"])
        if product is None:
            product = IthuteProduct(**item)
            db.add(product)
            changed = True
            continue
        for field in ("name", "category", "public_url", "api_url", "health_url", "deployment_target", "database_engine"):
            value = item.get(field)
            if getattr(product, field) != value:
                setattr(product, field, value)
                changed = True
        merged = dict(product.metadata_json or {})
        merged.update(item.get("metadata_json") or {})
        if merged != (product.metadata_json or {}):
            product.metadata_json = merged
            changed = True
    if changed:
        db.commit()
    return list(db.scalars(select(IthuteProduct).order_by(IthuteProduct.name)))


def latest_heartbeat(db: Session, product_id: str) -> IthuteProductHeartbeat | None:
    return db.scalar(
        select(IthuteProductHeartbeat)
        .where(IthuteProductHeartbeat.product_id == product_id)
        .order_by(IthuteProductHeartbeat.observed_at.desc())
        .limit(1)
    )


def product_snapshot(db: Session, product: IthuteProduct) -> dict[str, Any]:
    heartbeat = latest_heartbeat(db, product.id)
    status = product.operational_status.value
    if heartbeat is not None:
        status = heartbeat.status.value
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "version": (heartbeat.version if heartbeat and heartbeat.version else product.version),
        "status": status,
        "maintenance_mode": product.maintenance_mode,
        "public_url": product.public_url,
        "api_url": product.api_url,
        "health_url": product.health_url,
        "deployment_target": product.deployment_target,
        "database": {
            "ownership": product.database_ownership,
            "engine": product.database_engine,
            "status": heartbeat.database_status if heartbeat else "unknown",
        },
        "services": {
            "auth": heartbeat.auth_status if heartbeat else "configured",
            "push": heartbeat.push_status if heartbeat else "configured",
            "realtime": heartbeat.realtime_status if heartbeat else "configured",
            "event_bus": product.event_bus_mode,
        },
        "containers": heartbeat.container_summary_json if heartbeat else {},
        "metrics": heartbeat.metrics_json if heartbeat else {},
        "last_error": heartbeat.last_error if heartbeat else None,
        "last_seen_at": heartbeat.observed_at.isoformat() if heartbeat else None,
        "metadata": product.metadata_json or {},
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
