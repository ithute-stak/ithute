import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DeviceRequest(BaseModel):
    device_key: str = Field(min_length=8, max_length=200)
    platform: str = Field(pattern="^(android|ios|web)$")
    provider_endpoint: str = Field(min_length=8, max_length=8192)


class DeviceResponse(BaseModel):
    device_key: str
    application_id: str
    platform: str
    active: bool
    last_seen_at: datetime | None = None


class MessageRequest(BaseModel):
    recipient_sub: uuid.UUID
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=500)
    route: str | None = Field(default=None, max_length=500)
    sound: str | None = Field(default="default", max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=3600, ge=60, le=604800)

    @field_validator("data")
    @classmethod
    def limit_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 2048:
            raise ValueError("notification data must not exceed 2 KiB")
        return value


class DelegatedMessageRequest(MessageRequest):
    source_client_id: str = Field(min_length=2, max_length=120)


class MessageResponse(BaseModel):
    id: uuid.UUID
    status: str
    delivery_count: int
    deduplicated: bool = False


class DeliveryAckRequest(BaseModel):
    state: Literal["received", "opened"]


class DeliveryAckResponse(BaseModel):
    id: uuid.UUID
    state: str
    received_at: datetime | None
    opened_at: datetime | None


class DeliverySummary(BaseModel):
    status: str
    count: int


class MessageSummary(BaseModel):
    id: uuid.UUID
    source_client_id: str
    recipient_sub: uuid.UUID
    status: str
    deliveries: list[DeliverySummary]
    received_count: int = 0
    opened_count: int = 0


class AuthLifecycleEventRequest(BaseModel):
    event_id: uuid.UUID
    type: Literal[
        "session.revoked",
        "account.disabled",
        "account.enabled",
        "application.disabled",
        "application.enabled",
    ]
    sub: uuid.UUID | None = None
    sid: uuid.UUID | None = None
    client_id: str | None = Field(default=None, min_length=1, max_length=120)
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def sane_event_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        normalized = value.astimezone(timezone.utc)
        if normalized > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("occurred_at is too far in the future")
        return normalized

    @field_validator("details")
    @classmethod
    def limit_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 4096:
            raise ValueError("lifecycle event details must not exceed 4 KiB")
        return value

    @model_validator(mode="after")
    def required_identifiers(self) -> "AuthLifecycleEventRequest":
        if self.type == "session.revoked":
            if self.sub is None or self.sid is None or not self.client_id:
                raise ValueError("session.revoked requires sub, sid and client_id")
        elif self.type.startswith("account."):
            if self.sub is None:
                raise ValueError("account lifecycle events require sub")
            if self.sid is not None or self.client_id is not None:
                raise ValueError("account lifecycle events may contain only sub")
        elif self.type.startswith("application."):
            if not self.client_id:
                raise ValueError("application lifecycle events require client_id")
            if self.sub is not None or self.sid is not None:
                raise ValueError("application lifecycle events may contain only client_id")
        return self


class AuthLifecycleEventResponse(BaseModel):
    event_id: uuid.UUID
    applied: bool
    deduplicated: bool = False
