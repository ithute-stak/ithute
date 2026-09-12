from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models import MembershipRole, MembershipStatus


class InviteCreate(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.member


class InviteOut(BaseModel):
    id: str
    tenant_id: str
    email: EmailStr
    role: MembershipRole
    expires_at: str
    accepted_at: str | None = None
    token: str | None = None


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20)
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=256)


class MembershipOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    email: EmailStr
    full_name: str
    role: MembershipRole
    status: MembershipStatus


class MyMembershipOut(BaseModel):
    membership_id: str
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    tenant_status: str
    role: MembershipRole
    status: MembershipStatus


class MembershipUpdate(BaseModel):
    role: MembershipRole | None = None
    status: MembershipStatus | None = None


class ApiKeyCreate(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=2, max_length=100)
    scopes: list[str] = Field(default_factory=list, max_length=50)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: str
    expires_at: str | None = None
    revoked: bool
    key: str | None = None
