import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


_NAMESPACE_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-$")


def normalize_namespace_prefix(value: str) -> str:
    prefix = value.strip().lower()
    if not 4 <= len(prefix) <= 32:
        raise ValueError("local_part_prefix must be between 4 and 32 characters")
    if not _NAMESPACE_PREFIX_RE.fullmatch(prefix):
        raise ValueError("local_part_prefix must start with a letter or digit, use only letters, digits and hyphens, and end with a hyphen")
    return prefix


class PlatformMailDomainGrantCreate(BaseModel):
    service_client_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._:-]{0,119}$")
    domain_name: str = Field(min_length=3, max_length=253)
    local_part_prefix: str = Field(min_length=4, max_length=32)

    @field_validator("domain_name")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        if "." not in domain:
            raise ValueError("domain_name must be a fully-qualified domain")
        return domain

    @field_validator("local_part_prefix")
    @classmethod
    def normalize_prefix(cls, value: str) -> str:
        return normalize_namespace_prefix(value)


class PlatformMailDomainGrantResponse(BaseModel):
    id: uuid.UUID
    service_client_id: str
    domain_id: uuid.UUID
    domain_name: str
    local_part_prefix: str
    active: bool
    created_at: datetime


class PlatformMailboxProvisionRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)
    domain_name: str = Field(min_length=3, max_length=253)
    local_part: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=150)
    quota_bytes: int = Field(default=1024**3, ge=10 * 1024**2, le=50 * 1024**3)

    @field_validator("external_reference")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        return value.strip()

    @field_validator("domain_name")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        if "." not in domain:
            raise ValueError("domain_name must be a fully-qualified domain")
        return domain


class PlatformMailboxResponse(BaseModel):
    binding_id: uuid.UUID
    mailbox_id: uuid.UUID
    service_client_id: str
    external_reference: str
    address: str
    display_name: str | None
    quota_bytes: int
    status: str
    created_at: datetime
    credential_mode: str = "platform-managed"


class PlatformMailboxStatusResponse(BaseModel):
    binding_id: uuid.UUID
    mailbox_id: uuid.UUID
    address: str
    status: str


class PlatformMailSendRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    text: str | None = Field(default=None, max_length=1_000_000)
    html: str | None = Field(default=None, max_length=2_000_000)

    @field_validator("external_reference")
    @classmethod
    def normalize_external_reference(cls, value: str) -> str:
        return value.strip()

    @field_validator("recipient")
    @classmethod
    def normalize_recipient(cls, value: str) -> str:
        return value.strip().lower()


class PlatformMailSendResponse(BaseModel):
    delivery_id: uuid.UUID
    binding_id: uuid.UUID
    external_reference: str
    sender: str
    recipient: str
    status: str
    provider_message_id: str | None = None
    error: str | None = None
    created_at: datetime
