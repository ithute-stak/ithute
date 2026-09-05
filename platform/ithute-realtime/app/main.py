import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthError, AuthVerifier, ServicePrincipal, UserPrincipal
from .config import Settings, get_settings
from .db import SessionLocal, get_db
from .events import EventConflict, deliver_event, event_wire, pending_or_dead_counts, queue_event, replay_events
from .hub import ConnectionLimitError, hub
from .models import (
    AuditEvent,
    Conversation,
    ConversationMember,
    ConversationPin,
    EventRecipient,
    Message,
    MessageReaction,
    MessageReceipt,
    RealtimeEvent,
    utcnow,
)
from .rate_limit import RateLimitExceeded, enforce_rate_limit
from .schemas import (
    ActivityRequest,
    AttachmentRef,
    AuditOut,
    ConversationCreate,
    ConversationOut,
    EventAckOut,
    EventAckRequest,
    EventOut,
    EventRecipientOut,
    MemberMutationRequest,
    MemberOut,
    MessageCreate,
    MessageEditRequest,
    MessageOut,
    PinOut,
    PlatformConversationCreate,
    PlatformConversationEventCreate,
    PlatformEventRequest,
    PresenceOut,
    ReactionOut,
    ReactionRequest,
    ReadRequest,
    ReceiptOut,
    ReceiptRequest,
    TypingRequest,
)

bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()


app = FastAPI(
    title="!thute Realtime",
    version="2.0.0",
    description="Central Auth-protected WebSocket, chat, notification and broadcast backbone for Ithute products.",
    redoc_url=None,
    lifespan=lifespan,
)


@lru_cache
def verifier() -> AuthVerifier:
    return AuthVerifier(get_settings())


def _bearer(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return credentials.credentials


def _ensure_enabled(client_id: str) -> None:
    if client_id in get_settings().disabled_client_set:
        raise HTTPException(status_code=503, detail="realtime access is disabled for this application")


def user_principal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> UserPrincipal:
    try:
        principal = verifier().user(_bearer(credentials))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    _ensure_enabled(principal.client_id)
    return principal


def _service(required_scope: str):
    def dependency(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> ServicePrincipal:
        try:
            principal = verifier().service(_bearer(credentials), required_scope)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from None
        _ensure_enabled(principal.client_id)
        return principal
    return dependency


service_manage = _service("realtime.manage")
service_publish = _service("realtime.publish")
service_metrics = _service("realtime.metrics")


def _user_uuid(principal: UserPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="central subject is not a UUID") from None


def _members(db: Session, conversation_id: uuid.UUID) -> list[ConversationMember]:
    return list(
        db.scalars(
            select(ConversationMember)
            .where(ConversationMember.conversation_id == conversation_id)
            .order_by(ConversationMember.joined_at.asc())
        )
    )


def _member(db: Session, conversation: Conversation, principal: UserPrincipal) -> ConversationMember:
    user_id = _user_uuid(principal)
    row = db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.auth_user_id == user_id,
        )
    )
    if conversation.application_id != principal.client_id or row is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return row


def _conversation_out(db: Session, conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        application_id=conversation.application_id,
        kind=conversation.kind,
        title=conversation.title,
        description=conversation.description,
        room_key=conversation.room_key,
        archived=conversation.archived,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        members=[
            MemberOut(
                auth_user_id=item.auth_user_id,
                role=item.role,
                muted=item.muted,
                last_read_message_id=item.last_read_message_id,
            )
            for item in _members(db, conversation.id)
        ],
    )


def _safe_json(raw: str, fallback):
    try:
        value = json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback
    return value


def _message_out(message: Message) -> MessageOut:
    data = _safe_json(message.data_json, {})
    mentions = _safe_json(message.mentions_json, [])
    attachments = _safe_json(message.attachments_json, [])
    if message.deleted_at is not None:
        body = ""
        data = {}
        attachments = []
    else:
        body = message.body
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        application_id=message.application_id,
        sender_sub=message.sender_sub,
        sender_client_id=message.sender_client_id,
        sender_kind=message.sender_kind,
        message_type=message.message_type,
        version=message.version,
        priority=message.priority,
        body=body,
        data=data if isinstance(data, dict) else {},
        mentions=[uuid.UUID(str(value)) for value in mentions if value],
        attachments=[AttachmentRef.model_validate(item) for item in attachments if isinstance(item, dict)],
        reply_to_message_id=message.reply_to_message_id,
        forwarded_from_message_id=message.forwarded_from_message_id,
        client_message_id=message.client_message_id,
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
    )


def _event_out(event: RealtimeEvent) -> EventOut:
    payload = _safe_json(event.payload_json, {})
    return EventOut(
        id=event.id,
        cursor=event.cursor,
        application_id=event.application_id,
        event_type=event.event_type,
        version=event.version,
        priority=event.priority,
        audience_label=event.audience_label,
        payload=payload if isinstance(payload, dict) else {},
        status=event.status,
        deliver_at=event.deliver_at,
        expires_at=event.expires_at,
        delivered_at=event.delivered_at,
        created_at=event.created_at,
        recipients=[
            EventRecipientOut(auth_user_id=item.auth_user_id, received_at=item.received_at, opened_at=item.opened_at)
            for item in event.recipients
        ],
    )


def _audit(
    db: Session,
    *,
    application_id: str,
    actor_kind: str,
    actor_client_id: str,
    action: str,
    target_type: str,
    target_id: str,
    actor_sub: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            application_id=application_id,
            actor_kind=actor_kind,
            actor_sub=actor_sub,
            actor_client_id=actor_client_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details_json=json.dumps(details or {}, separators=(",", ":"), ensure_ascii=False, default=str),
        )
    )


def _create_conversation(db: Session, *, application_id: str, creator: uuid.UUID | None, payload: ConversationCreate) -> Conversation:
    settings = get_settings()
    participant_ids = list(dict.fromkeys(payload.participant_subs))
    if creator and creator not in participant_ids:
        participant_ids.insert(0, creator)
    if not participant_ids:
        raise HTTPException(status_code=422, detail="at least one conversation member is required")
    if len(participant_ids) > settings.max_group_members:
        raise HTTPException(status_code=422, detail="conversation member limit exceeded")
    if payload.kind == "direct" and len(participant_ids) != 2:
        raise HTTPException(status_code=422, detail="direct conversations require exactly two members")
    if payload.kind in {"channel", "system"} and not payload.room_key:
        raise HTTPException(status_code=422, detail="channel/system conversations require room_key")
    row = Conversation(
        application_id=application_id,
        kind=payload.kind,
        title=payload.title,
        description=payload.description,
        room_key=payload.room_key,
        created_by_sub=creator,
    )
    db.add(row)
    try:
        db.flush()
        for member_id in participant_ids:
            db.add(
                ConversationMember(
                    conversation_id=row.id,
                    auth_user_id=member_id,
                    role="owner" if creator and member_id == creator else "member",
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        if payload.room_key:
            existing = db.scalar(
                select(Conversation).where(
                    Conversation.application_id == application_id,
                    Conversation.room_key == payload.room_key,
                )
            )
            if existing is not None:
                return existing
        raise HTTPException(status_code=409, detail="conversation already exists") from None
    db.refresh(row)
    return row


def _message_recipients(db: Session, conversation_id: uuid.UUID) -> list[uuid.UUID]:
    return [item.auth_user_id for item in _members(db, conversation_id)]


async def _emit_message_event(
    db: Session,
    message: Message,
    *,
    event_type: str,
    push: bool = False,
    title: str | None = None,
    body: str | None = None,
) -> None:
    recipients = _message_recipients(db, message.conversation_id)
    event = queue_event(
        db,
        application_id=message.application_id,
        source_client_id=message.sender_client_id,
        event_type=event_type,
        version=message.version,
        priority=message.priority,
        recipients=recipients,
        payload={
            "conversation_id": str(message.conversation_id),
            "message": _message_out(message).model_dump(mode="json"),
            "title": title,
            "body": body if body is not None else message.body,
            "route": f"/chat/{message.conversation_id}",
            "data": {"conversation_id": str(message.conversation_id), "message_id": str(message.id)},
        },
        ttl_seconds=3600,
        push_enabled=push,
        idempotency_key=f"{event_type}:{message.id}:{message.edited_at or message.deleted_at or message.created_at}",
    )
    if event.status in {"queued", "retry"}:
        await deliver_event(db, event)


async def _emit_ephemeral(application_id: str, recipients: list[uuid.UUID], event_type: str, payload: dict) -> None:
    await hub.publish(
        application_id,
        {
            "type": event_type,
            "version": 1,
            "application_id": application_id,
            "recipients": [str(value) for value in recipients],
            **payload,
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ithute-realtime", "version": "2.0.0"}


@app.get("/readyz")
async def readyz(db: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    db.execute(text("SELECT 1"))
    redis_ready = bool(await hub.redis.ping())
    return {
        "status": "ready" if redis_ready else "not_ready",
        "service": "ithute-realtime",
        "redis": redis_ready,
        "auth": settings.auth_issuer,
        "push_enabled": settings.push_enabled,
        "disabled_clients": sorted(settings.disabled_client_set),
    }


@app.get("/v1/conversations", response_model=list[ConversationOut])
def list_conversations(
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversationOut]:
    user_id = _user_uuid(principal)
    rows = list(
        db.scalars(
            select(Conversation)
            .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
            .where(
                Conversation.application_id == principal.client_id,
                ConversationMember.auth_user_id == user_id,
                Conversation.archived.is_(False),
            )
            .order_by(Conversation.updated_at.desc())
        )
    )
    return [_conversation_out(db, row) for row in rows]


@app.post("/v1/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationOut:
    try:
        await enforce_rate_limit("conversation-create", f"{principal.client_id}:{principal.sub}", limit=30, window_seconds=60)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    row = _create_conversation(db, application_id=principal.client_id, creator=_user_uuid(principal), payload=payload)
    _audit(
        db,
        application_id=principal.client_id,
        actor_kind="user",
        actor_sub=_user_uuid(principal),
        actor_client_id=principal.client_id,
        action="conversation.created",
        target_type="conversation",
        target_id=str(row.id),
    )
    db.commit()
    return _conversation_out(db, row)


@app.get("/v1/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
    before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
) -> list[MessageOut]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    _member(db, conversation, principal)
    limit = min(limit, get_settings().max_history_page_size)
    stmt = select(Message).where(Message.conversation_id == conversation.id)
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    rows = list(db.scalars(stmt.order_by(Message.created_at.desc()).limit(limit)))
    rows.reverse()
    return [_message_out(row) for row in rows]


@app.post("/v1/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageOut:
    settings = get_settings()
    try:
        await enforce_rate_limit(
            "chat-send",
            f"{principal.client_id}:{principal.sub}",
            limit=settings.user_send_rate_limit,
            window_seconds=settings.user_send_rate_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None

    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.archived:
        raise HTTPException(status_code=404, detail="conversation not found")
    member = _member(db, conversation, principal)
    if member.role == "viewer":
        raise HTTPException(status_code=403, detail="viewer cannot send messages")

    if payload.client_message_id:
        existing = db.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.client_message_id == payload.client_message_id,
            )
        )
        if existing is not None:
            return _message_out(existing)

    member_ids = {item.auth_user_id for item in _members(db, conversation.id)}
    if any(value not in member_ids for value in payload.mention_subs):
        raise HTTPException(status_code=422, detail="mentions must reference conversation members")

    reply = db.get(Message, payload.reply_to_message_id) if payload.reply_to_message_id else None
    if payload.reply_to_message_id is not None and reply is None:
        raise HTTPException(status_code=404, detail="reply target not found")
    if reply is not None and reply.conversation_id != conversation.id:
        raise HTTPException(status_code=422, detail="reply target must be in this conversation")

    forwarded = db.get(Message, payload.forward_message_id) if payload.forward_message_id else None
    if payload.forward_message_id is not None and forwarded is None:
        raise HTTPException(status_code=404, detail="forward source not found")
    if forwarded is not None:
        if forwarded.application_id != principal.client_id:
            raise HTTPException(status_code=404, detail="forward source not found")
        source_conversation = db.get(Conversation, forwarded.conversation_id)
        if source_conversation is None:
            raise HTTPException(status_code=404, detail="forward source not found")
        _member(db, source_conversation, principal)

    body = payload.body.strip()
    attachments = [item.model_dump(mode="json") for item in payload.attachments]
    data = payload.data
    if forwarded is not None:
        if not body:
            body = forwarded.body
        if not attachments:
            attachments = _safe_json(forwarded.attachments_json, [])
        if not data:
            forwarded_data = _safe_json(forwarded.data_json, {})
            data = forwarded_data if isinstance(forwarded_data, dict) else {}

    sender_id = _user_uuid(principal)
    message = Message(
        conversation_id=conversation.id,
        application_id=principal.client_id,
        sender_sub=sender_id,
        sender_client_id=principal.client_id,
        sender_kind="user",
        message_type="chat.message",
        version=1,
        priority=payload.priority,
        body=body,
        data_json=json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str),
        mentions_json=json.dumps([str(value) for value in payload.mention_subs]),
        attachments_json=json.dumps(attachments, separators=(",", ":"), ensure_ascii=False),
        reply_to_message_id=payload.reply_to_message_id,
        forwarded_from_message_id=payload.forward_message_id,
        client_message_id=payload.client_message_id,
    )
    db.add(message)
    conversation.updated_at = utcnow()
    try:
        db.flush()
        for recipient in member_ids:
            db.add(
                MessageReceipt(
                    message_id=message.id,
                    auth_user_id=recipient,
                    state="read" if recipient == sender_id else "accepted",
                    delivered_at=utcnow() if recipient == sender_id else None,
                    read_at=utcnow() if recipient == sender_id else None,
                )
            )
        _audit(
            db,
            application_id=principal.client_id,
            actor_kind="user",
            actor_sub=sender_id,
            actor_client_id=principal.client_id,
            action="message.sent",
            target_type="message",
            target_id=str(message.id),
            details={"conversation_id": str(conversation.id), "priority": message.priority},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if payload.client_message_id:
            existing = db.scalar(
                select(Message).where(
                    Message.conversation_id == conversation.id,
                    Message.client_message_id == payload.client_message_id,
                )
            )
            if existing is not None:
                return _message_out(existing)
        raise
    db.refresh(message)
    await _emit_message_event(
        db,
        message,
        event_type="chat.message",
        push=True,
        title=conversation.title or "New message",
        body=message.body or "You have a new message",
    )
    return _message_out(message)


@app.patch("/v1/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: uuid.UUID,
    payload: MessageEditRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageOut:
    message = db.get(Message, message_id)
    if message is None or message.application_id != principal.client_id or message.deleted_at is not None:
        raise HTTPException(status_code=404, detail="message not found")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="message not found")
    member = _member(db, conversation, principal)
    actor = _user_uuid(principal)
    if message.sender_sub != actor and member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="message cannot be edited by this user")
    message.body = payload.body.strip()
    if payload.data is not None:
        message.data_json = json.dumps(payload.data, separators=(",", ":"), ensure_ascii=False, default=str)
    message.edited_at = utcnow()
    _audit(
        db,
        application_id=principal.client_id,
        actor_kind="user",
        actor_sub=actor,
        actor_client_id=principal.client_id,
        action="message.edited",
        target_type="message",
        target_id=str(message.id),
    )
    db.commit()
    db.refresh(message)
    await _emit_message_event(db, message, event_type="chat.message.edited")
    return _message_out(message)


@app.delete("/v1/messages/{message_id}", status_code=204)
async def delete_message(
    message_id: uuid.UUID,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    message = db.get(Message, message_id)
    if message is None or message.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="message not found")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="message not found")
    member = _member(db, conversation, principal)
    actor = _user_uuid(principal)
    if message.sender_sub != actor and member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="message cannot be deleted by this user")
    if message.deleted_at is None:
        message.deleted_at = utcnow()
        _audit(
            db,
            application_id=principal.client_id,
            actor_kind="user",
            actor_sub=actor,
            actor_client_id=principal.client_id,
            action="message.deleted",
            target_type="message",
            target_id=str(message.id),
        )
        db.commit()
        await _emit_message_event(db, message, event_type="chat.message.deleted")


@app.post("/v1/messages/{message_id}/receipts", response_model=ReceiptOut)
async def acknowledge_message(
    message_id: uuid.UUID,
    payload: ReceiptRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ReceiptOut:
    message = db.get(Message, message_id)
    if message is None or message.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="message not found")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="message not found")
    member = _member(db, conversation, principal)
    user_id = _user_uuid(principal)
    receipt = db.scalar(
        select(MessageReceipt).where(MessageReceipt.message_id == message.id, MessageReceipt.auth_user_id == user_id)
    )
    if receipt is None:
        receipt = MessageReceipt(message_id=message.id, auth_user_id=user_id)
        db.add(receipt)
    now = utcnow()
    if payload.state == "delivered":
        if receipt.delivered_at is None:
            receipt.delivered_at = now
        if receipt.state != "read":
            receipt.state = "delivered"
    else:
        receipt.delivered_at = receipt.delivered_at or now
        receipt.read_at = now
        receipt.state = "read"
        member.last_read_message_id = message.id
    receipt.device_key = payload.device_key
    db.commit()
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.receipt",
        {"conversation_id": str(conversation.id), "message_id": str(message.id), "actor_sub": principal.sub, "state": receipt.state},
    )
    return ReceiptOut(
        message_id=message.id,
        auth_user_id=user_id,
        state=receipt.state,
        delivered_at=receipt.delivered_at,
        read_at=receipt.read_at,
    )


@app.post("/v1/conversations/{conversation_id}/read", status_code=204)
async def mark_read(
    conversation_id: uuid.UUID,
    payload: ReadRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    member = _member(db, conversation, principal)
    message = db.get(Message, payload.message_id)
    if message is None or message.conversation_id != conversation.id:
        raise HTTPException(status_code=404, detail="message not found")
    member.last_read_message_id = message.id
    user_id = _user_uuid(principal)
    receipt = db.scalar(
        select(MessageReceipt).where(MessageReceipt.message_id == message.id, MessageReceipt.auth_user_id == user_id)
    )
    now = utcnow()
    if receipt is None:
        receipt = MessageReceipt(message_id=message.id, auth_user_id=user_id, state="read", delivered_at=now, read_at=now)
        db.add(receipt)
    else:
        receipt.state = "read"
        receipt.delivered_at = receipt.delivered_at or now
        receipt.read_at = now
    db.commit()
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.read",
        {"conversation_id": str(conversation.id), "reader_sub": principal.sub, "message_id": str(message.id)},
    )


@app.put("/v1/messages/{message_id}/reactions", response_model=ReactionOut)
async def add_reaction(
    message_id: uuid.UUID,
    payload: ReactionRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ReactionOut:
    message = db.get(Message, message_id)
    if message is None or message.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="message not found")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="message not found")
    _member(db, conversation, principal)
    user_id = _user_uuid(principal)
    reaction = db.scalar(
        select(MessageReaction).where(
            MessageReaction.message_id == message.id,
            MessageReaction.auth_user_id == user_id,
            MessageReaction.emoji == payload.emoji,
        )
    )
    if reaction is None:
        reaction = MessageReaction(message_id=message.id, auth_user_id=user_id, emoji=payload.emoji)
        db.add(reaction)
        db.commit()
        db.refresh(reaction)
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.reaction.added",
        {"conversation_id": str(conversation.id), "message_id": str(message.id), "actor_sub": principal.sub, "emoji": payload.emoji},
    )
    return ReactionOut(message_id=message.id, auth_user_id=user_id, emoji=reaction.emoji, created_at=reaction.created_at)


@app.delete("/v1/messages/{message_id}/reactions/{emoji}", status_code=204)
async def remove_reaction(
    message_id: uuid.UUID,
    emoji: str,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    message = db.get(Message, message_id)
    if message is None or message.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="message not found")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="message not found")
    _member(db, conversation, principal)
    user_id = _user_uuid(principal)
    db.execute(
        delete(MessageReaction).where(
            MessageReaction.message_id == message.id,
            MessageReaction.auth_user_id == user_id,
            MessageReaction.emoji == emoji,
        )
    )
    db.commit()
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.reaction.removed",
        {"conversation_id": str(conversation.id), "message_id": str(message.id), "actor_sub": principal.sub, "emoji": emoji},
    )


@app.put("/v1/conversations/{conversation_id}/pins/{message_id}", response_model=PinOut)
async def pin_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> PinOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    member = _member(db, conversation, principal)
    if member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="only conversation owners/admins can pin")
    message = db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise HTTPException(status_code=404, detail="message not found")
    pin = db.scalar(
        select(ConversationPin).where(
            ConversationPin.conversation_id == conversation.id,
            ConversationPin.message_id == message.id,
        )
    )
    if pin is None:
        pin = ConversationPin(conversation_id=conversation.id, message_id=message.id, pinned_by_sub=_user_uuid(principal))
        db.add(pin)
        db.commit()
        db.refresh(pin)
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.pin.added",
        {"conversation_id": str(conversation.id), "message_id": str(message.id), "actor_sub": principal.sub},
    )
    return PinOut(conversation_id=conversation.id, message_id=message.id, pinned_by_sub=pin.pinned_by_sub, created_at=pin.created_at)


@app.delete("/v1/conversations/{conversation_id}/pins/{message_id}", status_code=204)
async def unpin_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    member = _member(db, conversation, principal)
    if member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="only conversation owners/admins can unpin")
    db.execute(
        delete(ConversationPin).where(
            ConversationPin.conversation_id == conversation.id,
            ConversationPin.message_id == message_id,
        )
    )
    db.commit()
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.pin.removed",
        {"conversation_id": str(conversation.id), "message_id": str(message_id), "actor_sub": principal.sub},
    )


@app.post("/v1/conversations/{conversation_id}/activity", status_code=202)
async def activity(
    conversation_id: uuid.UUID,
    payload: ActivityRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    settings = get_settings()
    try:
        await enforce_rate_limit(
            "activity",
            f"{principal.client_id}:{principal.sub}",
            limit=settings.activity_rate_limit,
            window_seconds=settings.activity_rate_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    _member(db, conversation, principal)
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        f"chat.{payload.activity}.{payload.state}",
        {"conversation_id": str(conversation.id), "actor_sub": principal.sub},
    )
    return {"status": "accepted"}


@app.post("/v1/conversations/{conversation_id}/typing", status_code=202)
async def typing(
    conversation_id: uuid.UUID,
    payload: TypingRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    return await activity(conversation_id, ActivityRequest(activity="typing", state=payload.state), principal, db)


@app.get("/v1/conversations/{conversation_id}/presence", response_model=list[PresenceOut])
async def conversation_presence(
    conversation_id: uuid.UUID,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PresenceOut]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    _member(db, conversation, principal)
    output: list[PresenceOut] = []
    for item in _members(db, conversation.id):
        state = await hub.presence(principal.client_id, str(item.auth_user_id))
        last_seen = None
        raw_last = state.get("last_seen_at")
        if raw_last:
            try:
                last_seen = datetime.fromisoformat(str(raw_last))
            except ValueError:
                last_seen = None
        output.append(
            PresenceOut(
                auth_user_id=item.auth_user_id,
                online=bool(state["online"]),
                connection_count=int(state["connection_count"]),
                device_keys=list(state["device_keys"]),
                last_seen_at=last_seen,
            )
        )
    return output


@app.get("/v1/events/replay", response_model=list[EventOut])
def replay(
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
    after: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1),
) -> list[EventOut]:
    rows = replay_events(
        db,
        application_id=principal.client_id,
        auth_user_id=_user_uuid(principal),
        after=after,
        limit=min(limit, get_settings().max_replay_page_size),
    )
    return [_event_out(row) for row in rows]


@app.post("/v1/events/{event_id}/ack", response_model=EventAckOut)
def acknowledge_event(
    event_id: uuid.UUID,
    payload: EventAckRequest,
    principal: Annotated[UserPrincipal, Depends(user_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> EventAckOut:
    user_id = _user_uuid(principal)
    recipient = db.scalar(
        select(EventRecipient)
        .join(RealtimeEvent, RealtimeEvent.id == EventRecipient.event_id)
        .where(
            EventRecipient.event_id == event_id,
            EventRecipient.auth_user_id == user_id,
            RealtimeEvent.application_id == principal.client_id,
        )
    )
    if recipient is None:
        raise HTTPException(status_code=404, detail="event not found")
    now = utcnow()
    recipient.received_at = recipient.received_at or now
    if payload.state == "opened":
        recipient.opened_at = now
    db.commit()
    return EventAckOut(event_id=event_id, state=payload.state, received_at=recipient.received_at, opened_at=recipient.opened_at)


@app.post("/v1/platform/conversations", response_model=ConversationOut, status_code=201)
def platform_create_conversation(
    payload: PlatformConversationCreate,
    principal: Annotated[ServicePrincipal, Depends(service_manage)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationOut:
    row = _create_conversation(db, application_id=principal.client_id, creator=None, payload=payload)
    _audit(
        db,
        application_id=principal.client_id,
        actor_kind="service",
        actor_client_id=principal.client_id,
        action="conversation.platform_created",
        target_type="conversation",
        target_id=str(row.id),
        details={"room_key": row.room_key, "kind": row.kind},
    )
    db.commit()
    return _conversation_out(db, row)


@app.patch("/v1/platform/conversations/{conversation_id}/members", response_model=ConversationOut)
async def platform_manage_members(
    conversation_id: uuid.UUID,
    payload: MemberMutationRequest,
    principal: Annotated[ServicePrincipal, Depends(service_manage)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    current = {item.auth_user_id: item for item in _members(db, conversation.id)}
    for mutation in payload.members:
        row = current.get(mutation.auth_user_id)
        if mutation.action == "add":
            if row is None:
                db.add(
                    ConversationMember(
                        conversation_id=conversation.id,
                        auth_user_id=mutation.auth_user_id,
                        role=mutation.role or "member",
                        muted=bool(mutation.muted) if mutation.muted is not None else False,
                    )
                )
        elif mutation.action == "remove":
            if row is not None:
                db.delete(row)
        elif row is not None:
            if mutation.role is not None:
                row.role = mutation.role
            if mutation.muted is not None:
                row.muted = mutation.muted
    conversation.updated_at = utcnow()
    _audit(
        db,
        application_id=principal.client_id,
        actor_kind="service",
        actor_client_id=principal.client_id,
        action="conversation.members_changed",
        target_type="conversation",
        target_id=str(conversation.id),
        details={"changes": [item.model_dump(mode="json") for item in payload.members]},
    )
    db.commit()
    await _emit_ephemeral(
        principal.client_id,
        _message_recipients(db, conversation.id),
        "chat.members.updated",
        {"conversation_id": str(conversation.id)},
    )
    return _conversation_out(db, conversation)


@app.post("/v1/platform/conversations/{conversation_id}/events", response_model=MessageOut, status_code=201)
async def platform_publish_conversation_event(
    conversation_id: uuid.UUID,
    payload: PlatformConversationEventCreate,
    principal: Annotated[ServicePrincipal, Depends(service_publish)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    if payload.client_message_id:
        existing = db.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.client_message_id == payload.client_message_id,
            )
        )
        if existing is not None:
            return _message_out(existing)
    message = Message(
        conversation_id=conversation.id,
        application_id=principal.client_id,
        sender_sub=None,
        sender_client_id=principal.client_id,
        sender_kind="service",
        message_type=payload.event_type,
        version=payload.version,
        priority=payload.priority,
        body=payload.body,
        data_json=json.dumps(payload.data, separators=(",", ":"), ensure_ascii=False, default=str),
        client_message_id=payload.client_message_id,
    )
    db.add(message)
    conversation.updated_at = utcnow()
    db.commit()
    db.refresh(message)
    await _emit_message_event(db, message, event_type=payload.event_type)
    return _message_out(message)


@app.post("/v1/platform/events", response_model=EventOut, status_code=202)
async def platform_publish_event(
    payload: PlatformEventRequest,
    principal: Annotated[ServicePrincipal, Depends(service_publish)],
    db: Annotated[Session, Depends(get_db)],
) -> EventOut:
    settings = get_settings()
    if payload.event_type.startswith("broadcast.") and "realtime.broadcast" not in principal.scopes:
        raise HTTPException(status_code=403, detail="realtime.broadcast scope required")
    try:
        await enforce_rate_limit(
            "service-publish",
            principal.client_id,
            limit=settings.service_publish_rate_limit,
            window_seconds=settings.service_publish_rate_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    if len(payload.recipient_subs) > settings.max_event_recipients:
        raise HTTPException(status_code=422, detail="event recipient limit exceeded")
    try:
        event = queue_event(
            db,
            application_id=principal.client_id,
            source_client_id=principal.client_id,
            event_type=payload.event_type,
            version=payload.version,
            priority=payload.priority,
            recipients=payload.recipient_subs,
            payload={"title": payload.title, "body": payload.body, "route": payload.route, "data": payload.data},
            ttl_seconds=payload.ttl_seconds,
            deliver_at=payload.deliver_at,
            push_enabled=payload.push,
            broadcast_connected=payload.broadcast_connected,
            audience_label=payload.audience_label,
            idempotency_key=payload.idempotency_key,
        )
    except EventConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    _audit(
        db,
        application_id=principal.client_id,
        actor_kind="service",
        actor_client_id=principal.client_id,
        action="broadcast.queued" if payload.event_type.startswith("broadcast.") else "event.queued",
        target_type="event",
        target_id=str(event.id),
        details={
            "event_type": payload.event_type,
            "recipient_count": len(payload.recipient_subs),
            "audience_label": payload.audience_label,
            "broadcast_connected": payload.broadcast_connected,
            "scheduled": payload.deliver_at is not None,
        },
    )
    db.commit()
    if event.status == "queued":
        await deliver_event(db, event)
    return _event_out(event)


@app.get("/v1/platform/events/{event_id}", response_model=EventOut)
def platform_event_status(
    event_id: uuid.UUID,
    principal: Annotated[ServicePrincipal, Depends(service_publish)],
    db: Annotated[Session, Depends(get_db)],
) -> EventOut:
    event = db.get(RealtimeEvent, event_id)
    if event is None or event.application_id != principal.client_id:
        raise HTTPException(status_code=404, detail="event not found")
    return _event_out(event)


@app.get("/v1/platform/metrics")
async def platform_metrics(
    principal: Annotated[ServicePrincipal, Depends(service_metrics)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return {"application_id": principal.client_id, "socket": await hub.metrics(), "events": pending_or_dead_counts(db, principal.client_id)}


@app.get("/v1/platform/audit", response_model=list[AuditOut])
def platform_audit(
    principal: Annotated[ServicePrincipal, Depends(service_metrics)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditOut]:
    rows = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.application_id == principal.client_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
    )
    return [
        AuditOut(
            id=row.id,
            application_id=row.application_id,
            actor_kind=row.actor_kind,
            actor_sub=row.actor_sub,
            actor_client_id=row.actor_client_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            details=_safe_json(row.details_json, {}),
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    principal: UserPrincipal | None = None
    connection_id: str | None = None
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=get_settings().websocket_auth_timeout_seconds)
        if frame.get("type") != "auth" or not isinstance(frame.get("access_token"), str):
            await websocket.close(code=4401, reason="authentication frame required")
            return
        try:
            principal = verifier().user(frame["access_token"])
            _ensure_enabled(principal.client_id)
        except (AuthError, HTTPException):
            await websocket.close(code=4401, reason="invalid or disabled central auth token")
            return

        device_key = str(frame.get("device_key") or f"legacy:{uuid.uuid4()}")
        if len(device_key) > 200:
            await websocket.close(code=4400, reason="device_key is too long")
            return
        try:
            connection_id = await hub.connect(principal.client_id, principal.sub, websocket, device_key)
        except ConnectionLimitError as exc:
            await websocket.close(code=4429, reason=str(exc))
            return

        heartbeat = max(15, get_settings().websocket_presence_ttl_seconds // 2)
        await websocket.send_json(
            {
                "type": "ready",
                "version": 2,
                "application_id": principal.client_id,
                "sub": principal.sub,
                "connection_id": connection_id,
                "heartbeat_seconds": heartbeat,
                "replay_endpoint": "/v1/events/replay",
            }
        )

        after = frame.get("after")
        if isinstance(after, str) and after:
            with SessionLocal() as db:
                rows = replay_events(
                    db,
                    application_id=principal.client_id,
                    auth_user_id=uuid.UUID(principal.sub),
                    after=after,
                    limit=get_settings().max_replay_page_size,
                )
                for event in rows:
                    await websocket.send_json({"type": "replay", "event": event_wire(event)})

        while True:
            try:
                frame = await asyncio.wait_for(websocket.receive_json(), timeout=get_settings().websocket_idle_timeout_seconds)
            except asyncio.TimeoutError:
                await websocket.close(code=4408, reason="heartbeat timeout")
                return
            if frame.get("type") == "ping":
                await hub.refresh_presence(principal.client_id, principal.sub, connection_id)
                await websocket.send_json({"type": "pong", "connection_id": connection_id})
            elif frame.get("type") == "ack" and isinstance(frame.get("event_id"), str):
                try:
                    event_id = uuid.UUID(frame["event_id"])
                except ValueError:
                    await websocket.send_json({"type": "error", "detail": "invalid event_id"})
                    continue
                state = frame.get("state")
                if state not in {"received", "opened"}:
                    await websocket.send_json({"type": "error", "detail": "ack state must be received or opened"})
                    continue
                with SessionLocal() as db:
                    recipient = db.scalar(
                        select(EventRecipient)
                        .join(RealtimeEvent, RealtimeEvent.id == EventRecipient.event_id)
                        .where(
                            EventRecipient.event_id == event_id,
                            EventRecipient.auth_user_id == uuid.UUID(principal.sub),
                            RealtimeEvent.application_id == principal.client_id,
                        )
                    )
                    if recipient is None:
                        await websocket.send_json({"type": "error", "detail": "event not found"})
                        continue
                    now = utcnow()
                    recipient.received_at = recipient.received_at or now
                    if state == "opened":
                        recipient.opened_at = now
                    db.commit()
                await websocket.send_json({"type": "ack.accepted", "event_id": str(event_id), "state": state})
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "use REST endpoints for persistent commands; socket accepts ping and event acknowledgements",
                    }
                )
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if principal is not None and connection_id is not None:
            await hub.disconnect(principal.client_id, principal.sub, connection_id)
