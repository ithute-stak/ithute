import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_EVENT_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")


def _bounded_json(value: Any, *, limit: int = 16384) -> Any:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"encoded JSON must not exceed {limit} bytes")
    return value


class AttachmentRef(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    thumbnail_url: str | None = Field(default=None, max_length=2048)

    @field_validator("url", "thumbnail_url")
    @classmethod
    def safe_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("https://") or value.startswith("/"):
            return value
        raise ValueError("attachment references must use HTTPS or an application-relative route")


class ConversationCreate(BaseModel):
    participant_subs: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    room_key: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: Literal["direct", "group", "channel", "system"] = "group"

    @field_validator("participant_subs")
    @classmethod
    def unique_participants(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))


class PlatformConversationCreate(ConversationCreate):
    pass


class MemberMutation(BaseModel):
    auth_user_id: uuid.UUID
    action: Literal["add", "remove", "update"]
    role: Literal["owner", "admin", "member", "viewer"] | None = None
    muted: bool | None = None


class MemberMutationRequest(BaseModel):
    members: list[MemberMutation] = Field(min_length=1, max_length=500)


class MemberOut(BaseModel):
    auth_user_id: uuid.UUID
    role: str
    muted: bool
    last_read_message_id: uuid.UUID | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    application_id: str
    kind: str
    title: str | None
    description: str | None = None
    room_key: str | None = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    members: list[MemberOut]


class MessageCreate(BaseModel):
    body: str = Field(default="", max_length=4000)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=120)
    data: dict[str, Any] = Field(default_factory=dict)
    reply_to_message_id: uuid.UUID | None = None
    forward_message_id: uuid.UUID | None = None
    mention_subs: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    attachments: list[AttachmentRef] = Field(default_factory=list, max_length=10)
    priority: Literal["low", "normal", "high", "critical"] = "normal"

    @field_validator("mention_subs")
    @classmethod
    def unique_mentions(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(value)

    @model_validator(mode="after")
    def body_or_attachment(self) -> "MessageCreate":
        if not self.body.strip() and not self.attachments and self.forward_message_id is None:
            raise ValueError("message requires body, attachment, or forward_message_id")
        return self


class MessageEditRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any] | None = None

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _bounded_json(value)


class PlatformConversationEventCreate(BaseModel):
    event_type: str = Field(min_length=3, max_length=80)
    version: int = Field(default=1, ge=1, le=99)
    body: str = Field(default="", max_length=4000)
    data: dict[str, Any] = Field(default_factory=dict)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=120)
    priority: Literal["low", "normal", "high", "critical"] = "normal"

    @field_validator("event_type")
    @classmethod
    def event_name(cls, value: str) -> str:
        if not _EVENT_RE.fullmatch(value):
            raise ValueError("event_type must be a dotted/namespaced lowercase event name")
        return value

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(value)


PlatformEventCreate = PlatformConversationEventCreate


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    application_id: str
    sender_sub: uuid.UUID | None
    sender_client_id: str
    sender_kind: str
    message_type: str
    version: int = 1
    priority: str = "normal"
    body: str
    data: dict[str, Any]
    mentions: list[uuid.UUID] = Field(default_factory=list)
    attachments: list[AttachmentRef] = Field(default_factory=list)
    reply_to_message_id: uuid.UUID | None = None
    forwarded_from_message_id: uuid.UUID | None = None
    client_message_id: str | None
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None


class ReadRequest(BaseModel):
    message_id: uuid.UUID


class ReceiptRequest(BaseModel):
    state: Literal["delivered", "read"]
    device_key: str | None = Field(default=None, max_length=200)


class ReceiptOut(BaseModel):
    message_id: uuid.UUID
    auth_user_id: uuid.UUID
    state: str
    delivered_at: datetime | None = None
    read_at: datetime | None = None


class ReactionRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)


class ReactionOut(BaseModel):
    message_id: uuid.UUID
    auth_user_id: uuid.UUID
    emoji: str
    created_at: datetime


class PinOut(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    pinned_by_sub: uuid.UUID | None
    created_at: datetime


class ActivityRequest(BaseModel):
    activity: Literal["typing", "recording", "uploading", "viewing"]
    state: Literal["start", "stop"]


class TypingRequest(BaseModel):
    state: Literal["start", "stop"]


class PlatformEventRequest(BaseModel):
    event_type: str = Field(min_length=3, max_length=80)
    version: int = Field(default=1, ge=1, le=99)
    recipient_subs: list[uuid.UUID] = Field(default_factory=list, max_length=5000)
    title: str | None = Field(default=None, max_length=160)
    body: str = Field(default="", max_length=1000)
    route: str | None = Field(default=None, max_length=500)
    data: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    ttl_seconds: int = Field(default=3600, ge=30, le=604800)
    deliver_at: datetime | None = None
    push: bool = False
    broadcast_connected: bool = False
    audience_label: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("event_type")
    @classmethod
    def event_name(cls, value: str) -> str:
        if not _EVENT_RE.fullmatch(value):
            raise ValueError("event_type must be a dotted/namespaced lowercase event name")
        return value

    @field_validator("recipient_subs")
    @classmethod
    def unique_recipients(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded_json(value)

    @model_validator(mode="after")
    def validate_audience(self) -> "PlatformEventRequest":
        if not self.recipient_subs and not self.broadcast_connected:
            raise ValueError("recipient_subs are required unless broadcast_connected=true")
        return self


class EventRecipientOut(BaseModel):
    auth_user_id: uuid.UUID
    received_at: datetime | None = None
    opened_at: datetime | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    cursor: str
    application_id: str
    event_type: str
    version: int
    priority: str
    audience_label: str | None
    payload: dict[str, Any]
    status: str
    deliver_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    recipients: list[EventRecipientOut] = Field(default_factory=list)


class EventAckRequest(BaseModel):
    state: Literal["received", "opened"]


class EventAckOut(BaseModel):
    event_id: uuid.UUID
    state: str
    received_at: datetime | None
    opened_at: datetime | None


class PresenceOut(BaseModel):
    auth_user_id: uuid.UUID
    online: bool
    connection_count: int
    device_keys: list[str] = Field(default_factory=list)
    last_seen_at: datetime | None = None


class AuditOut(BaseModel):
    id: uuid.UUID
    application_id: str
    actor_kind: str
    actor_sub: uuid.UUID | None
    actor_client_id: str
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any]
    created_at: datetime
