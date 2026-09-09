from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.domains import DomainDnsMode, DomainStatus, DomainVerificationMethod


class DomainCreate(BaseModel):
    name: str = Field(min_length=1, max_length=320)
    dns_mode: DomainDnsMode = DomainDnsMode.platform
    verification_method: DomainVerificationMethod | None = None
    mail_enabled: bool = True
    notes: str | None = Field(default=None, max_length=4000)


class DomainUpdate(BaseModel):
    dns_mode: DomainDnsMode | None = None
    mail_enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DomainStatusUpdate(BaseModel):
    status: DomainStatus

    @field_validator("status")
    @classmethod
    def block_pending_manual_transition(cls, value: DomainStatus) -> DomainStatus:
        if value == DomainStatus.pending_verification:
            raise ValueError("Use challenge regeneration to return to pending verification")
        return value


class DomainVerifyRequest(BaseModel):
    # Required only for TXT-verification domains. Nameserver-verification domains
    # prove ownership by delegating to both configured Ithute nameservers.
    token: str | None = Field(default=None, min_length=20, max_length=200)


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ascii_name: str
    unicode_name: str
    status: DomainStatus
    dns_mode: DomainDnsMode
    mail_enabled: bool
    notes: str | None
    verification_method: DomainVerificationMethod
    verification_record_name: str
    verification_token_hint: str
    ownership_verified_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class DomainCreateResponse(DomainRead):
    verification_value: str | None = None


class DomainChallengeResponse(BaseModel):
    domain_id: UUID
    record_name: str
    record_type: str = "TXT"
    verification_value: str


class DomainVerifyResponse(BaseModel):
    verified: bool
    status: DomainStatus
    observed_values: list[str]
    ownership_verified_at: datetime | None


class DomainListResponse(BaseModel):
    items: list[DomainRead]
    total: int
    limit: int
    offset: int


class DomainEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain_id: UUID
    tenant_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata_json: str | None
    created_at: datetime


class DomainVerificationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain_id: UUID
    actor_user_id: UUID
    success: bool
    observed_values_json: str
    error: str | None
    created_at: datetime


class DomainReadiness(BaseModel):
    domain_id: UUID
    ownership_verified: bool
    domain_status: DomainStatus
    dns_mode: DomainDnsMode
    ready_for_powerdns: bool
    required_nameservers: list[str]
    next_phase: str
