from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


Channel = Literal["push", "email", "sms"]


class NotificationRequest(BaseModel):
    source_client_id: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9._:-]*$")
    recipient_sub: uuid.UUID | None = None
    recipient_email: EmailStr | None = None
    recipient_phone: str | None = Field(default=None, max_length=32)
    channels: list[Channel] = Field(min_length=1, max_length=3)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=2000)
    route: str | None = Field(default=None, max_length=500)
    sound: str | None = Field(default="default", max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=3600, ge=60, le=604800)

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value: list[Channel]) -> list[Channel]:
        return list(dict.fromkeys(value))

    @field_validator("data")
    @classmethod
    def bounded_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 4096:
            raise ValueError("notification data must not exceed 4 KiB")
        return value

    @model_validator(mode="after")
    def channel_targets(self) -> "NotificationRequest":
        if "push" in self.channels and self.recipient_sub is None:
            raise ValueError("recipient_sub is required for push")
        if "email" in self.channels and self.recipient_email is None:
            raise ValueError("recipient_email is required for email")
        if "sms" in self.channels and not self.recipient_phone:
            raise ValueError("recipient_phone is required for sms")
        return self


class DeliveryResponse(BaseModel):
    channel: str
    status: str
    attempt_count: int
    provider_reference: str | None = None
    last_error: str | None = None


class NotificationResponse(BaseModel):
    id: uuid.UUID
    status: str
    source_client_id: str
    deliveries: list[DeliveryResponse]
    deduplicated: bool = False
