import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PlatformMailDomainGrantCreate(BaseModel):
    service_client_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._:-]{0,119}$")
    domain_name: str = Field(min_length=3, max_length=253)

    @field_validator("domain_name")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        if "." not in domain:
            raise ValueError("domain_name must be a fully-qualified domain")
        return domain


class PlatformMailDomainGrantResponse(BaseModel):
    id: uuid.UUID
    service_client_id: str
    domain_id: uuid.UUID
    domain_name: str
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
