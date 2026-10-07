import re
from time import perf_counter
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, BeforeValidator, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import MailNode, MailRelationship, MailThreatModelVersion, MailThreatShadowPrediction, PhishingFinding
from app.models.mail import Mailbox, MailboxStatus, MailboxStorageType
from app.services.mailboxes import normalize_destination
from app.services.mail_first_contact import (
    decorate_first_contact_html,
    decorate_first_contact_text,
    prepare_first_contact,
    record_successful_send,
)
from app.services.mail_intelligence import analyze_mail_message
from app.services.mail_intelligence_learning import feature_snapshot, training_readiness
from app.services.mail_identity_risk import publish_verified_mail_risk
from app.services.mail_sender_behavior import observe_sender_behavior
from app.services.mail_threat_model import predict
from app.services.mail_threat_shadow import baseline_probabilities
from app.services.mail_threat_canary import automatic_rollback, baseline_floor, deterministic_canary_member, serving_source
from app.services.security_audit import record_webmail_security_event
from app.services.security_controls import SecurityControlUnavailable, clear_webmail_login_failures, record_webmail_login_failure, webmail_login_allowed
from app.services.webmail import (
    WebmailError,
    attachment,
    create_session,
    delete_message,
    delete_session,
    display_name,
    folders,
    message,
    messages,
    messages_with_bodies,
    move_message,
    save_display_name,
    save_draft,
    send_message,
    session_credentials,
    set_flags,
)
from app.services.webmail_polish import (
    add_relationship_note,
    add_relationship_task,
    contact_presence,
    contacts,
    folder_counts,
    internal_chat_messages,
    relationship_notes,
    relationship_tasks,
    save_contact,
    save_signature,
    send_internal_chat,
    send_rich_message,
    set_contact_pinned,
    shared_contacts,
    signature,
)

router = APIRouter(prefix="/webmail", tags=["webmail"])
UID_RE = re.compile(r"^[0-9]+$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")


def _normalize_webmail_address(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("destination must be an email address")
    try:
        return normalize_destination(value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


WebmailAddress = Annotated[str, BeforeValidator(_normalize_webmail_address)]


class WebmailLogin(BaseModel):
    address: WebmailAddress = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class WebmailAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_b64: str = Field(min_length=1, max_length=25_000_000)


class WebmailSend(BaseModel):
    to: list[WebmailAddress] = Field(min_length=1, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    bcc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    attachments: list[WebmailAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class WebmailRichSend(BaseModel):
    to: list[WebmailAddress] = Field(min_length=1, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    bcc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)
    signature_html: str = Field(default="", max_length=20000)
    attachments: list[WebmailAttachment] = Field(default_factory=list, max_length=20)
    in_reply_to: str = Field(default="", max_length=998)
    references: str = Field(default="", max_length=4000)


class WebmailDraft(BaseModel):
    to: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    cc: list[WebmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)


class WebmailFlags(BaseModel):
    seen: bool | None = None
    flagged: bool | None = None
    answered: bool | None = None


class WebmailMove(BaseModel):
    destination: str = Field(min_length=1, max_length=255)


class WebmailSignature(BaseModel):
    html: str = Field(default="", max_length=20000)


class WebmailIdentity(BaseModel):
    display_name: str = Field(default="", max_length=255)


class WebmailContact(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=255)


class WebmailBusinessPin(BaseModel):
    email: EmailStr
    pinned: bool = True


class WebmailBusinessNote(BaseModel):
    email: EmailStr
    text: str = Field(min_length=1, max_length=2000)


class WebmailBusinessTask(BaseModel):
    email: EmailStr
    text: str = Field(min_length=1, max_length=1000)
    due_at: str = Field(default="", max_length=64)


class WebmailBusinessChat(BaseModel):
    email: EmailStr
    text: str = Field(min_length=1, max_length=4000)


class MailIntelligenceVerdict(BaseModel):
    label: str = Field(pattern=r"^(legitimate|phishing|bec)$")
    confidence: float = Field(ge=0.80, le=1.0)


def _failure(exc: WebmailError, status: int = 503) -> HTTPException:
    text = str(exc)
    if "session" in text.lower() or "authentication" in text.lower():
        status = 401
    elif "not found" in text.lower():
        status = 404
    return HTTPException(status_code=status, detail=text)


def _credentials(token: str | None) -> tuple[str, str]:
    try:
        return session_credentials(token or "")
    except WebmailError as exc:
        raise _failure(exc, 401) from exc


def _uid(value: str) -> str:
    if not UID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="Invalid IMAP UID")
    return value


def _client_ip(request: Request) -> str:
    # Only trust the direct peer. Trusted proxy forwarding is configured at the
    # edge rather than accepting spoofable X-Forwarded-For values here.
    return request.client.host if request.client else "unknown"


def _security_event(db: Session, request: Request, address: str, action: str, outcome: str, retry_after: int | None = None) -> None:
    try:
        record_webmail_security_event(
            db,
            action=action,
            address=address,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
            outcome=outcome,
            retry_after=retry_after,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Security audit service is unavailable") from exc


def _resolve_shadow_predictions(
    db: Session,
    *,
    mailbox_id,
    message_ref: str,
    label: str,
) -> None:
    rows = db.scalars(
        select(MailThreatShadowPrediction).where(
            MailThreatShadowPrediction.mailbox_id == mailbox_id,
            MailThreatShadowPrediction.message_ref == message_ref,
            MailThreatShadowPrediction.verified_label.is_(None),
        )
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.verified_label = label
        row.resolved_at = now


def _automatic_rollback_models(db: Session, *, tenant_id) -> None:
    models = db.scalars(
        select(MailThreatModelVersion).where(
            MailThreatModelVersion.tenant_id == tenant_id,
            MailThreatModelVersion.lifecycle_state.in_(["canary", "active"]),
        )
    ).all()
    now = datetime.now(timezone.utc)
    for model in models:
        start_at = model.canary_started_at if model.lifecycle_state == "canary" else model.activated_at
        if start_at is None:
            continue
        predictions = db.scalars(
            select(MailThreatShadowPrediction)
            .where(
                MailThreatShadowPrediction.model_id == model.id,
                MailThreatShadowPrediction.verified_label.is_not(None),
                MailThreatShadowPrediction.created_at >= start_at,
            )
            .order_by(MailThreatShadowPrediction.created_at.asc())
        ).all()
        rows = []
        for row in predictions:
            if model.lifecycle_state == "canary" and not deterministic_canary_member(
                model_id=str(model.id),
                mailbox_id=str(row.mailbox_id),
                message_ref=row.message_ref,
            ):
                continue
            rows.append({
                "verified_label": row.verified_label,
                "candidate_probabilities": row.probabilities_json,
                "baseline_probabilities": row.baseline_json,
                "latency_ms": row.latency_ms,
            })
        decision = automatic_rollback(rows)
        if not decision["rollback"]:
            continue
        model.lifecycle_state = "retired_or_rolled_back"
        model.retired_at = now
        model.rollback_reason = "Automatic rollback: " + ", ".join(decision["reasons"])
        model.shadow_metrics_json = decision.get("validation") or model.shadow_metrics_json
        model.promotion_evidence_json = {
            **(model.promotion_evidence_json or {}),
            "automatic_rollback": decision,
        }


def _prediction_for_model(
    db: Session,
    *,
    model: MailThreatModelVersion,
    mailbox: Mailbox,
    message_ref: str,
    features: dict,
    baseline: dict,
) -> dict:
    existing = db.scalar(
        select(MailThreatShadowPrediction).where(
            MailThreatShadowPrediction.model_id == model.id,
            MailThreatShadowPrediction.mailbox_id == mailbox.id,
            MailThreatShadowPrediction.message_ref == message_ref,
        )
    )
    if existing is not None:
        return {
            "model_id": str(model.id),
            "version": model.version,
            "lifecycle_state": model.lifecycle_state,
            "probabilities": existing.probabilities_json,
            "baseline": existing.baseline_json,
            "latency_ms": existing.latency_ms,
        }

    started = perf_counter()
    probabilities = predict(model.artifact_json or {}, features)
    latency_ms = round((perf_counter() - started) * 1000.0, 3)
    db.add(
        MailThreatShadowPrediction(
            tenant_id=mailbox.tenant_id,
            mailbox_id=mailbox.id,
            model_id=model.id,
            message_ref=message_ref,
            probabilities_json=probabilities,
            baseline_json=baseline,
            feature_snapshot_json=features,
            latency_ms=latency_ms,
        )
    )
    return {
        "model_id": str(model.id),
        "version": model.version,
        "lifecycle_state": model.lifecycle_state,
        "probabilities": probabilities,
        "baseline": baseline,
        "latency_ms": latency_ms,
    }


def _shadow_score_message(
    db: Session,
    *,
    mailbox: Mailbox,
    message_payload: dict,
    intelligence: dict,
) -> dict | None:
    challenger = db.scalar(
        select(MailThreatModelVersion)
        .where(
            MailThreatModelVersion.tenant_id == mailbox.tenant_id,
            MailThreatModelVersion.lifecycle_state.in_(["shadow", "qualified", "canary"]),
        )
        .order_by(MailThreatModelVersion.created_at.desc())
        .limit(1)
    )
    active = db.scalar(
        select(MailThreatModelVersion)
        .where(
            MailThreatModelVersion.tenant_id == mailbox.tenant_id,
            MailThreatModelVersion.lifecycle_state == "active",
        )
        .order_by(MailThreatModelVersion.activated_at.desc(), MailThreatModelVersion.created_at.desc())
        .limit(1)
    )
    if challenger is None and active is None:
        return None

    message_ref = str(
        message_payload.get("message_id")
        or f"uid:{message_payload.get('uid') or ''}"
    )[:512]
    features = feature_snapshot(message_payload, intelligence)
    security = intelligence.get("security") if isinstance(intelligence.get("security"), dict) else {}
    baseline = baseline_probabilities(
        float(security.get("phishing_probability") or 0.0),
        float(security.get("bec_probability") or 0.0),
    )

    challenger_result = (
        _prediction_for_model(
            db,
            model=challenger,
            mailbox=mailbox,
            message_ref=message_ref,
            features=features,
            baseline=baseline,
        )
        if challenger is not None
        else None
    )
    active_result = (
        _prediction_for_model(
            db,
            model=active,
            mailbox=mailbox,
            message_ref=message_ref,
            features=features,
            baseline=baseline,
        )
        if active is not None and (challenger is None or active.id != challenger.id)
        else None
    )
    db.commit()

    canary_applied = (
        challenger is not None
        and challenger.lifecycle_state == "canary"
        and deterministic_canary_member(
            model_id=str(challenger.id),
            mailbox_id=str(mailbox.id),
            message_ref=message_ref,
        )
    )
    route = serving_source(
        challenger_state=challenger.lifecycle_state if challenger is not None else None,
        canary_member=canary_applied,
        active_present=active_result is not None,
    )
    serving_result = (
        challenger_result
        if route == "challenger"
        else active_result
        if route == "active"
        else None
    )

    effective_security = None
    if serving_result is not None:
        effective_security = baseline_floor(
            security,
            serving_result.get("probabilities") or {},
        )
        intelligence["security"] = {
            **security,
            "phishing_probability": effective_security["phishing_probability"],
            "bec_probability": effective_security["bec_probability"],
            "recommended_action": effective_security["recommended_action"],
        }

    primary = challenger_result or active_result
    if primary is None:
        return None
    primary_state = str(primary.get("lifecycle_state") or "")
    return {
        **primary,
        "shadow_only": (
            primary_state in {"shadow", "qualified"}
            or (primary_state == "canary" and not canary_applied)
        ),
        "canary_applied": canary_applied,
        "effective_security": effective_security,
        "baseline_preserved": True,
        "serving_model_id": serving_result.get("model_id") if serving_result else None,
        "active_champion": (
            {
                "model_id": active_result["model_id"],
                "version": active_result["version"],
                "probabilities": active_result["probabilities"],
                "latency_ms": active_result["latency_ms"],
            }
            if active_result is not None and primary.get("model_id") != active_result.get("model_id")
            else None
        ),
    }

def _safe_attachment_name(filename: str) -> str:
    value = CONTROL_CHARS_RE.sub(" ", filename or "").replace("/", "_").replace("\\", "_").strip(" .")
    if not value or value in {".", ".."}:
        return "attachment.bin"
    return value[:180]


def _mailbox_transport(db: Session, address: str) -> dict:
    mailbox = db.scalar(
        select(Mailbox).where(
            Mailbox.address == address.lower(),
            Mailbox.status == MailboxStatus.active,
        )
    )
    if mailbox is None or mailbox.storage_type != MailboxStorageType.external:
        return {
            "imap_host": settings.webmail_imap_host,
            "imap_port": settings.webmail_imap_port,
            "smtp_host": settings.webmail_smtp_host,
            "smtp_port": settings.webmail_smtp_port,
        }
    if mailbox.mail_node_id is None:
        raise HTTPException(status_code=503, detail="Mailbox storage node is not assigned")
    node = db.scalar(
        select(MailNode).where(
            MailNode.id == mailbox.mail_node_id,
            MailNode.status == "active",
            (MailNode.tenant_id.is_(None)) | (MailNode.tenant_id == mailbox.tenant_id),
        )
    )
    if node is None:
        raise HTTPException(status_code=503, detail="Mailbox storage node is unavailable")
    return {
        "imap_host": node.hostname,
        "imap_port": 993,
        "smtp_host": node.hostname,
        "smtp_port": 587,
    }


@router.post("/session")
def login(payload: WebmailLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    address = payload.address
    client_ip = _client_ip(request)
    try:
        allowed, retry_after = webmail_login_allowed(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not allowed:
        _security_event(db, request, address, "security.webmail.login.blocked", "rate_limited", retry_after)
        raise HTTPException(status_code=429, detail="Too many mailbox login attempts. Try again later.", headers={"Retry-After": str(retry_after)})
    transport = _mailbox_transport(db, address)
    try:
        token = create_session(address, payload.password, **transport)
    except WebmailError as exc:
        try:
            _, locked = record_webmail_login_failure(address, client_ip)
        except SecurityControlUnavailable as control_exc:
            raise HTTPException(status_code=503, detail=str(control_exc)) from control_exc
        if locked:
            _security_event(db, request, address, "security.webmail.login.locked", "failed", settings.webmail_login_lock_seconds)
            raise HTTPException(status_code=429, detail="Too many mailbox login attempts. Try again later.", headers={"Retry-After": str(settings.webmail_login_lock_seconds)}) from exc
        _security_event(db, request, address, "security.webmail.login.failed", "failed")
        raise _failure(exc, 401) from exc
    try:
        clear_webmail_login_failures(address, client_ip)
    except SecurityControlUnavailable as exc:
        delete_session(token)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _security_event(db, request, address, "security.webmail.login.succeeded", "succeeded")
    response.set_cookie(settings.webmail_session_cookie_name, token, max_age=settings.webmail_session_ttl_seconds, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/api/v1/webmail")
    return {"authenticated": True, "address": address}


@router.get("/session")
def session(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    return {"authenticated": True, "address": address}


@router.delete("/session", status_code=204)
def logout(request: Request, response: Response, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None, db: Session = Depends(get_db)):
    address = None
    if token:
        try:
            address, _ = session_credentials(token)
        except WebmailError:
            address = None
        try:
            delete_session(token)
        except WebmailError as exc:
            raise _failure(exc) from exc
    if address:
        _security_event(db, request, address, "security.webmail.logout", "succeeded")
    response.delete_cookie(settings.webmail_session_cookie_name, path="/api/v1/webmail")


@router.get("/folders")
def list_folders(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return {"items": folders(address, password)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/folder-counts")
def counts(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return {"items": folder_counts(address, password)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages")
def list_messages(folder: str = Query(default="INBOX", min_length=1, max_length=255), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000), q: str = Query(default="", max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return messages(address, password, folder=folder, limit=limit, offset=offset, query=q)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}")
def get_message(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, password = _credentials(token)
    try:
        payload = message(address, password, uid=_uid(uid), folder=folder)
        intelligence = analyze_mail_message(payload, mailbox_address=address)
        behavior = observe_sender_behavior(address, payload)
        if behavior is not None:
            if bool((intelligence.get("trust") or {}).get("verified")):
                retained = [
                    signal for signal in (behavior.get("signals") or [])
                    if signal.get("signal") != "first_seen_sender"
                ]
                score = min(100, sum(int(signal.get("weight") or 0) for signal in retained))
                behavior = {
                    **behavior,
                    "score": score,
                    "state": "high" if score >= 50 else "elevated" if score >= 25 else "watch" if score >= 12 else "stable",
                    "signals": retained,
                    "trusted_identity_context": True,
                }
            intelligence["behavior"] = behavior
        payload["intelligence"] = intelligence
        mailbox = db.scalar(
            select(Mailbox).where(
                Mailbox.address == address.lower(),
                Mailbox.status == MailboxStatus.active,
            )
        )
        if mailbox is not None:
            try:
                shadow = _shadow_score_message(
                    db,
                    mailbox=mailbox,
                    message_payload=payload,
                    intelligence=intelligence,
                )
                if shadow is not None:
                    payload["intelligence"]["supervised_shadow"] = shadow
            except Exception:
                db.rollback()
                payload["intelligence"]["supervised_shadow"] = {
                    "available": False,
                    "shadow_only": True,
                    "fallback": "ithute-mail-intelligence-v1",
                }
        return payload
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}/intelligence")
def get_message_intelligence(
    uid: str,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = _credentials(token)
    try:
        payload = message(address, password, uid=_uid(uid), folder=folder)
        return analyze_mail_message(payload, mailbox_address=address)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/intelligence")
def analyze_message_batch(
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    limit: int = Query(default=20, ge=1, le=25),
    offset: int = Query(default=0, ge=0, le=100000),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = _credentials(token)
    try:
        listing = messages_with_bodies(
            address,
            password,
            folder=folder,
            limit=limit,
            offset=offset,
            query="",
        )
        source_items = listing.get("items", []) if isinstance(listing, dict) else []
        analyzed = [
            {
                "uid": str(item.get("uid") or ""),
                "subject": item.get("subject"),
                "from": item.get("from"),
                "date": item.get("date"),
                "intelligence": analyze_mail_message(item, mailbox_address=address),
            }
            for item in source_items
        ]
        return {
            "folder": folder,
            "items": analyzed,
            "failures": [],
            "count": len(analyzed),
            "requested": len(source_items),
            "total": int(listing.get("total") or 0),
            "offset": offset,
            "limit": limit,
            "skipped": int(listing.get("skipped") or 0),
            "automatic_blocking": False,
        }
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/messages/{uid}/intelligence/verdict")
def save_message_intelligence_verdict(
    uid: str,
    payload: MailIntelligenceVerdict,
    folder: str = Query(default="INBOX", min_length=1, max_length=255),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, password = _credentials(token)
    mailbox = db.scalar(
        select(Mailbox).where(
            Mailbox.address == address.lower(),
            Mailbox.status == MailboxStatus.active,
        )
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox was not found")

    try:
        message_payload = message(address, password, uid=_uid(uid), folder=folder)
    except WebmailError as exc:
        raise _failure(exc) from exc

    intelligence = analyze_mail_message(message_payload, mailbox_address=address)
    message_ref = str(message_payload.get("message_id") or f"{folder}:{uid}")[:512]
    existing = db.scalar(
        select(PhishingFinding).where(
            PhishingFinding.mailbox_id == mailbox.id,
            PhishingFinding.message_ref == message_ref,
            PhishingFinding.finding_type == "mail_intelligence_training_label",
        )
    )
    if existing is not None:
        existing_label = str((existing.metadata_json or {}).get("verified_label") or existing.action_taken or "")
        if existing_label != payload.label:
            raise HTTPException(status_code=409, detail="Verified mail intelligence verdict is immutable")
        _resolve_shadow_predictions(
            db,
            mailbox_id=mailbox.id,
            message_ref=message_ref,
            label=existing_label,
        )
        _automatic_rollback_models(db, tenant_id=mailbox.tenant_id)
        db.commit()
        existing_confidence = float((existing.metadata_json or {}).get("label_confidence") or payload.confidence)
        risk_published = publish_verified_mail_risk(
            mailbox_address=address,
            message_ref=message_ref,
            label=existing_label,
            confidence=existing_confidence,
        )
        return {
            "saved": True,
            "finding_id": str(existing.id),
            "message_ref": message_ref,
            "label": existing_label,
            "confidence": existing_confidence,
            "already_verified": True,
            "identity_risk_published": risk_published,
        }

    snapshot = feature_snapshot(message_payload, intelligence)
    finding = PhishingFinding(
        tenant_id=mailbox.tenant_id,
        mailbox_id=mailbox.id,
        message_ref=message_ref,
        severity="info",
        finding_type="mail_intelligence_training_label",
        sender=str(message_payload.get("from") or "")[:320] or None,
        subject=str(message_payload.get("subject") or "")[:500] or None,
        indicators_json=list(snapshot.get("signal_names") or []),
        action_taken=payload.label,
        resolved=True,
        resolved_at=datetime.now(timezone.utc),
        metadata_json={
            "verified_label": payload.label,
            "label_confidence": payload.confidence,
            "feature_snapshot": snapshot,
            "verified_by_mailbox": address.lower(),
            "raw_body_stored": False,
        },
    )
    db.add(finding)
    _resolve_shadow_predictions(
        db,
        mailbox_id=mailbox.id,
        message_ref=message_ref,
        label=payload.label,
    )
    _automatic_rollback_models(db, tenant_id=mailbox.tenant_id)
    db.commit()
    db.refresh(finding)
    risk_published = publish_verified_mail_risk(
        mailbox_address=address,
        message_ref=message_ref,
        label=payload.label,
        confidence=payload.confidence,
    )
    return {
        "saved": True,
        "finding_id": str(finding.id),
        "message_ref": message_ref,
        "label": payload.label,
        "confidence": payload.confidence,
        "already_verified": False,
        "identity_risk_published": risk_published,
    }


@router.get("/intelligence/training-status")
def mail_intelligence_training_status(
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, _password = _credentials(token)
    mailbox = db.scalar(
        select(Mailbox).where(
            Mailbox.address == address.lower(),
            Mailbox.status == MailboxStatus.active,
        )
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox was not found")

    findings = db.scalars(
        select(PhishingFinding)
        .where(
            PhishingFinding.tenant_id == mailbox.tenant_id,
            PhishingFinding.finding_type == "mail_intelligence_training_label",
            PhishingFinding.resolved.is_(True),
        )
        .order_by(PhishingFinding.created_at.asc())
    ).all()
    rows = [
        {
            "label": str((finding.metadata_json or {}).get("verified_label") or finding.action_taken or ""),
            "confidence": float((finding.metadata_json or {}).get("label_confidence") or 0.0),
        }
        for finding in findings
    ]
    return training_readiness(rows)


@router.patch("/messages/{uid}/flags")
def update_flags(uid: str, payload: WebmailFlags, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return set_flags(address, password, _uid(uid), folder, payload.seen, payload.flagged, payload.answered)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/messages/{uid}/move")
def move(uid: str, payload: WebmailMove, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return move_message(address, password, _uid(uid), folder, payload.destination)
    except WebmailError as exc:
        raise _failure(exc, 409) from exc


@router.delete("/messages/{uid}")
def remove(uid: str, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return delete_message(address, password, _uid(uid), folder)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/messages/{uid}/attachments/{index}")
def download_attachment(uid: str, index: int, folder: str = Query(default="INBOX", min_length=1, max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        filename, _content_type, payload = attachment(address, password, _uid(uid), folder, index)
    except WebmailError as exc:
        raise _failure(exc) from exc
    safe_name = _safe_attachment_name(filename)
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/drafts", status_code=201)
def draft(payload: WebmailDraft, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, password = _credentials(token)
    try:
        return save_draft(address, password, [str(value).lower() for value in payload.to], [str(value).lower() for value in payload.cc], payload.subject, payload.body_text)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/identity")
def get_identity(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"address": address, "display_name": display_name(address)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/identity")
def put_identity(payload: WebmailIdentity, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        result = save_display_name(address, payload.display_name)
        return {"address": address, **result}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/signature")
def get_signature(token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"html": signature(address)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/signature")
def put_signature(payload: WebmailSignature, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return save_signature(address, payload.html)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/contacts")
def get_contacts(q: str = Query(default="", max_length=255), token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return {"items": contacts(address, q)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/business-contacts")
def get_business_contacts(
    limit: int = Query(default=12, ge=1, le=50),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        rows = contacts(address)
        presence = contact_presence([str(row.get("email") or "") for row in rows])
        enriched = []
        for row in rows:
            email_address = str(row.get("email") or "").lower()
            interactions = int(row.get("interactions") or 0)
            last_seen = str(row.get("last_seen") or "")
            source_set = {str(item) for item in row.get("sources", [])}
            enriched.append({
                **row,
                "online": bool(presence.get(email_address, False)),
                "business": bool("incoming" in source_set or "outgoing" in source_set),
                "score": interactions * 10 + (100000 if presence.get(email_address, False) else 0) + (1000000 if row.get("pinned") else 0),
                "last_seen": last_seen,
                "company": email_address.rsplit("@", 1)[-1] if "@" in email_address else "",
            })
        enriched.sort(
            key=lambda row: (
                bool(row.get("pinned")),
                bool(row["online"]),
                int(row["score"]),
                str(row["last_seen"]),
                str(row.get("name") or "").lower(),
                str(row.get("email") or "").lower(),
            ),
            reverse=True,
        )
        return {"items": enriched[:limit]}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/business-conversation")
def get_business_conversation(
    email: WebmailAddress,
    limit: int = Query(default=25, ge=1, le=50),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = _credentials(token)
    try:
        available = folders(address, password)
        names = [str(item.get("name") or "") for item in available]
        inbox_name = next((name for name in names if name.lower() == "inbox"), "INBOX")
        sent_name = next((name for name in names if "sent" in name.lower()), "")
        inbox = messages(address, password, folder=inbox_name, limit=limit, offset=0, query=email)
        sent = messages(address, password, folder=sent_name, limit=limit, offset=0, query=email) if sent_name else {"items": []}
        rows = [
            *[{**row, "folder": inbox_name} for row in inbox.get("items", [])],
            *[{**row, "folder": sent_name} for row in sent.get("items", [])],
        ]
        rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
        return {"items": rows[:limit], "email": email}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/business-contacts/pin")
def pin_business_contact(
    payload: WebmailBusinessPin,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        return set_contact_pinned(address, str(payload.email), payload.pinned)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


def _business_conversation_rows(address: str, password: str, email_address: str, limit: int = 50) -> list[dict]:
    available = folders(address, password)
    names = [str(item.get("name") or "") for item in available]
    inbox_name = next((name for name in names if name.lower() == "inbox"), "INBOX")
    sent_name = next((name for name in names if "sent" in name.lower()), "")
    inbox = messages(address, password, folder=inbox_name, limit=limit, offset=0, query=email_address)
    sent = messages(address, password, folder=sent_name, limit=limit, offset=0, query=email_address) if sent_name else {"items": []}
    rows = [
        *[{**row, "folder": inbox_name, "direction": "incoming"} for row in inbox.get("items", [])],
        *[{**row, "folder": sent_name, "direction": "outgoing"} for row in sent.get("items", [])],
    ]
    rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return rows[:limit]


@router.get("/business-workspace")
def get_business_workspace(
    email: WebmailAddress,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = _credentials(token)
    try:
        rows = _business_conversation_rows(address, password, email, 50)
        contact = next((item for item in contacts(address) if str(item.get("email") or "").lower() == email.lower()), None) or {
            "email": email,
            "name": "",
            "interactions": len(rows),
            "last_seen": "",
            "pinned": False,
            "domain": email.rsplit("@", 1)[-1] if "@" in email else "",
        }
        domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        company_people = [
            item for item in contacts(address)
            if str(item.get("email") or "").lower().endswith(f"@{domain}")
        ][:50]
        documents = []
        for row in rows:
            for item in row.get("attachments") or []:
                documents.append({
                    **item,
                    "message_uid": row.get("uid"),
                    "folder": row.get("folder"),
                    "subject": row.get("subject") or "",
                    "date": row.get("date") or "",
                    "direction": row.get("direction"),
                })
        latest = rows[0] if rows else {}
        unread_from_them = sum(1 for row in rows if row.get("direction") == "incoming" and not row.get("seen", True))
        status = "No conversation yet"
        stale = False
        last_seen = str(contact.get("last_seen") or "")
        if last_seen:
            try:
                seen_at = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if seen_at.tzinfo is None:
                    seen_at = seen_at.replace(tzinfo=timezone.utc)
                stale = (datetime.now(timezone.utc) - seen_at).days >= 30
            except ValueError:
                stale = False
        if unread_from_them:
            status = "You owe a reply"
        elif latest and latest.get("direction") == "outgoing":
            status = "Waiting for reply"
        elif stale:
            status = "No contact for 30+ days"
        elif latest:
            status = "Conversation active"
        timeline = [
            {
                "type": "email",
                "direction": row.get("direction"),
                "subject": row.get("subject") or "(no subject)",
                "date": row.get("date") or "",
                "uid": row.get("uid"),
                "folder": row.get("folder"),
                "attachments": len(row.get("attachments") or []),
            }
            for row in rows
        ]
        owner_domain = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
        internal = bool(domain and domain == owner_domain)
        return {
            "contact": contact,
            "company": {"domain": domain, "people": company_people},
            "overview": {
                "emails": len(rows),
                "documents": len(documents),
                "status": status,
                "online": bool(contact_presence([email]).get(email.lower(), False)),
                "internal_chat": internal,
                "unread_from_them": unread_from_them,
                "stale": stale,
            },
            "emails": rows,
            "documents": documents,
            "notes": relationship_notes(address, email),
            "tasks": relationship_tasks(address, email),
            "timeline": timeline,
            "shared_contacts": shared_contacts(address),
            "chat": internal_chat_messages(address, email) if internal else [],
        }
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/business-notes", status_code=201)
def create_business_note(
    payload: WebmailBusinessNote,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        return add_relationship_note(address, str(payload.email), payload.text)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


@router.post("/business-tasks", status_code=201)
def create_business_task(
    payload: WebmailBusinessTask,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        return add_relationship_task(address, str(payload.email), payload.text, payload.due_at)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


@router.get("/business-chat")
def get_business_chat(
    email: WebmailAddress,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        return {"items": internal_chat_messages(address, email)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/business-chat", status_code=201)
def create_business_chat(
    payload: WebmailBusinessChat,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, _ = _credentials(token)
    try:
        return send_internal_chat(address, str(payload.email), payload.text)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


@router.get("/relationships")
def mail_relationships(
    limit: int = Query(default=100, ge=1, le=500),
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, _ = _credentials(token)
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == address.lower()))
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    rows = db.scalars(
        select(MailRelationship)
        .where(MailRelationship.mailbox_id == mailbox.id)
        .order_by(MailRelationship.last_sent_at.desc().nullslast(), MailRelationship.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "peer_address": row.peer_address,
                "state": row.state,
                "messages_sent": row.messages_sent,
                "replies_received": row.replies_received,
                "first_contact_at": row.first_contact_at.isoformat() if row.first_contact_at else None,
                "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
                "last_reply_at": row.last_reply_at.isoformat() if row.last_reply_at else None,
            }
            for row in rows
        ]
    }


@router.post("/contacts", status_code=201)
def put_contact(payload: WebmailContact, token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None):
    address, _ = _credentials(token)
    try:
        return save_contact(address, str(payload.email), payload.name)
    except WebmailError as exc:
        raise _failure(exc, 422) from exc


@router.post("/send", status_code=202)
def compose(
    payload: WebmailSend,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, password = _credentials(token)
    recipients = [str(value).lower() for value in payload.to]
    cc = [str(value).lower() for value in payload.cc]
    bcc = [str(value).lower() for value in payload.bcc]
    try:
        mailbox, first_contact = prepare_first_contact(
            db,
            sender_address=address,
            visible_recipients=[*recipients, *cc],
            hidden_recipients=bcc,
        )
        body_text = decorate_first_contact_text(payload.body_text, first_contact)
        result = send_message(address, password, recipients, cc, bcc, payload.subject, body_text, [item.model_dump() for item in payload.attachments], payload.in_reply_to, payload.references)
        record_successful_send(db, mailbox=mailbox, recipients=[*recipients, *cc, *bcc])
        return {**result, "first_contact": first_contact.public_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/send-rich", status_code=202)
def compose_rich(
    payload: WebmailRichSend,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
    db: Session = Depends(get_db),
):
    address, password = _credentials(token)
    to = [str(v).lower() for v in payload.to]
    cc = [str(v).lower() for v in payload.cc]
    bcc = [str(v).lower() for v in payload.bcc]
    try:
        mailbox, first_contact = prepare_first_contact(
            db,
            sender_address=address,
            visible_recipients=[*to, *cc],
            hidden_recipients=bcc,
        )
        result = send_rich_message(
            address,
            password,
            to,
            cc,
            bcc,
            payload.subject,
            decorate_first_contact_text(payload.body_text, first_contact),
            decorate_first_contact_html(payload.body_html, first_contact),
            payload.signature_html,
            [item.model_dump() for item in payload.attachments],
            payload.in_reply_to,
            payload.references,
        )
        record_successful_send(db, mailbox=mailbox, recipients=[*to, *cc, *bcc])
        return {**result, "first_contact": first_contact.public_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WebmailError as exc:
        raise _failure(exc) from exc
