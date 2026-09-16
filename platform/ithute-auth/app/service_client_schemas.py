from datetime import datetime

from pydantic import BaseModel, Field


_CAPABILITY_PATTERN = r"^[a-z0-9][a-z0-9._:-]{0,119}$"
_SCOPE_PATTERN = r"^[a-z0-9][a-z0-9._:-]*(?: [a-z0-9][a-z0-9._:-]*)*$"
_CLIENT_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,119}$"


class ManagedServiceTokenRequest(BaseModel):
    client_id: str = Field(min_length=2, max_length=120, pattern=_CLIENT_PATTERN)
    client_secret: str = Field(min_length=24, max_length=512)
    audience: str = Field(min_length=1, max_length=120, pattern=_CAPABILITY_PATTERN)
    scope: str = Field(min_length=1, max_length=1000, pattern=_SCOPE_PATTERN)


class AdminServiceClientCreateRequest(BaseModel):
    client_id: str = Field(min_length=2, max_length=120, pattern=_CLIENT_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    allowed_audiences: list[str] = Field(min_length=1, max_length=32)
    allowed_scopes: list[str] = Field(min_length=1, max_length=64)
    expires_at: datetime | None = None
    credential_expires_at: datetime | None = None


class AdminServiceClientUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    allowed_audiences: list[str] | None = Field(default=None, min_length=1, max_length=32)
    allowed_scopes: list[str] | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None
    expires_at: datetime | None = None
    clear_expiry: bool = False


class AdminServiceCredentialResponse(BaseModel):
    id: str
    secret_prefix: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class AdminServiceClientResponse(BaseModel):
    client_id: str
    name: str
    description: str | None
    allowed_audiences: list[str]
    allowed_scopes: list[str]
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    credentials: list[AdminServiceCredentialResponse]


class AdminServiceClientCreateResponse(BaseModel):
    client: AdminServiceClientResponse
    client_secret: str


class AdminServiceSecretRotateRequest(BaseModel):
    expires_at: datetime | None = None
    revoke_previous: bool = True


class AdminServiceSecretResponse(BaseModel):
    client_id: str
    credential_id: str
    secret_prefix: str
    client_secret: str
    expires_at: datetime | None


class AdminServiceClientAuditResponse(BaseModel):
    id: str
    event_type: str
    success: bool
    client_id: str | None
    ip_address: str | None
    details: dict[str, object] | None
    created_at: datetime
