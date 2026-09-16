from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class TrustedIdentityInvitationRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    preferred_channel: str = Field(default="phone", pattern=r"^(phone|email)$")

    @model_validator(mode="after")
    def validate_delivery_target(self) -> "TrustedIdentityInvitationRequest":
        if not self.email and not self.phone:
            raise ValueError("email or phone is required")
        if self.preferred_channel == "phone":
            if not self.phone:
                raise ValueError("phone is required when preferred_channel is phone")
            # Auth keeps only the contact actually verified by this invitation.
            # Other business contact details belong in the product database and
            # can be added to central identity later through normal verification.
            self.email = None
        else:
            if not self.email:
                raise ValueError("email is required when preferred_channel is email")
            self.phone = None
        return self


class IdentityInvitationResponse(BaseModel):
    id: uuid.UUID
    source_client_id: str
    external_reference: str
    display_name: str
    email: str | None
    phone: str | None
    preferred_channel: str
    status: str
    delivery_status: str
    expires_at: datetime
    existing_identity: bool
    # Only the source service can read this response. It stays null until the
    # invitation is actually consumed, then exposes the immutable Ithute Auth
    # subject so the source product can link membership without guessing by
    # email or phone.
    activated_sub: str | None = None


class IdentityInvitationActivationRequest(BaseModel):
    invitation_id: uuid.UUID
    code: str | None = Field(default=None, min_length=6, max_length=16)
    token: str | None = Field(default=None, min_length=20, max_length=512)
    password: str | None = Field(default=None, min_length=10, max_length=128)

    @model_validator(mode="after")
    def challenge_required(self) -> "IdentityInvitationActivationRequest":
        if not self.code and not self.token:
            raise ValueError("activation code or token is required")
        return self


class IdentityInvitationActivationResponse(BaseModel):
    sub: str
    status: str = "active"
    existing_identity: bool
    sign_in_url: str
