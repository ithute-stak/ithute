from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from database.multi_tenant_school_management.models.enum.user_role import UserRole
from database.multi_tenant_school_management.schemas.person import PersonCreate, PersonRead


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: UserRole
    school_id: Optional[UUID] = None
    channel: Optional[str] = "students"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserBase


class UserCreate(UserBase):
    password: str
    person: PersonCreate


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class UserRead(UserBase):
    id: UUID
    auth_user_id: Optional[UUID] = None
    person: Optional[PersonRead] = None

    model_config = {"from_attributes": True}


class RefreshTokenOut(BaseModel):
    id: str
    jti: str
    revoked: bool
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
