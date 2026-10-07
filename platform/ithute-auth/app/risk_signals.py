from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ExternalRiskSignal, User, utcnow
from .security import normalize_email
from .security_service import record_audit
from .service_authorization import ServiceContext, require_managed_service_scope


router = APIRouter(prefix="/v1/internal/security", tags=["security-risk-signals"])

_ALLOWED_SIGNALS: dict[str, dict[str, object]] = {
    "mail.phishing.verified": {"severity": "high", "weight": 30, "ttl_hours": 24},
    "mail.bec.verified": {"severity": "high", "weight": 35, "ttl_hours": 36},
}


class RiskSignalIn(BaseModel):
    subject_email: EmailStr
    source_ref: str = Field(min_length=16, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    signal_type: str = Field(min_length=3, max_length=80)
    confidence: int = Field(ge=80, le=100)
    verified_by_human: bool
    metadata: dict[str, object] = Field(default_factory=dict)


class RiskSignalOut(BaseModel):
    accepted: bool
    matched_identity: bool
    signal_id: str | None = None
    risk_weight: int = 0
    expires_at: str | None = None
    duplicate: bool = False


@router.post("/risk-signals", response_model=RiskSignalOut, status_code=202)
def ingest_verified_risk_signal(
    payload: RiskSignalIn,
    context: ServiceContext = Depends(require_managed_service_scope("security.risk.write")),
    db: Session = Depends(get_db),
) -> RiskSignalOut:
    policy = _ALLOWED_SIGNALS.get(payload.signal_type)
    # The central identity service, not the publisher, decides which external
    # evidence can influence authentication and by how much.
    if policy is None or not payload.verified_by_human:
        return RiskSignalOut(accepted=False, matched_identity=False)

    email = normalize_email(str(payload.subject_email))
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is None:
        record_audit(
            db,
            event_type="external_risk_signal_unmatched",
            client_id=context.client_id,
            details={"signal_type": payload.signal_type},
        )
        db.commit()
        return RiskSignalOut(accepted=True, matched_identity=False)

    existing = db.scalar(
        select(ExternalRiskSignal).where(
            ExternalRiskSignal.source_client_id == context.client_id,
            ExternalRiskSignal.source_ref == payload.source_ref,
        )
    )
    if existing is not None:
        return RiskSignalOut(
            accepted=True,
            matched_identity=existing.user_id == user.id,
            signal_id=str(existing.id),
            risk_weight=existing.risk_weight,
            expires_at=existing.expires_at.isoformat(),
            duplicate=True,
        )

    now = utcnow()
    weight = int(policy["weight"])
    expires_at = now + timedelta(hours=int(policy["ttl_hours"]))
    safe_metadata = {
        key: value
        for key, value in payload.metadata.items()
        if key in {"mailbox_domain", "verdict", "evidence_version"}
        and isinstance(value, (str, int, float, bool))
    }
    row = ExternalRiskSignal(
        user_id=user.id,
        source_client_id=context.client_id,
        source_ref=payload.source_ref,
        signal_type=payload.signal_type,
        severity=str(policy["severity"]),
        confidence=payload.confidence,
        verified=True,
        risk_weight=weight,
        metadata_json=json.dumps(safe_metadata, separators=(",", ":"), sort_keys=True),
        expires_at=expires_at,
        created_at=now,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        event_type="external_risk_signal_received",
        user=user,
        client_id=context.client_id,
        details={
            "signal_id": str(row.id),
            "signal_type": row.signal_type,
            "risk_weight": row.risk_weight,
            "expires_at": row.expires_at.isoformat(),
            "human_verified": True,
        },
    )
    db.commit()
    db.refresh(row)
    return RiskSignalOut(
        accepted=True,
        matched_identity=True,
        signal_id=str(row.id),
        risk_weight=row.risk_weight,
        expires_at=row.expires_at.isoformat(),
    )
