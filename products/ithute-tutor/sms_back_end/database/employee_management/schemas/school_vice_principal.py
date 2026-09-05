from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict

from database.multi_tenant_school_management.schemas.user import UserRole


class VicePrincipalPersonCreate(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None


class VicePrincipalUserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.vice_principal
    person: VicePrincipalPersonCreate


class VicePrincipalCreate(BaseModel):
    school_id: UUID
    employee_number: Optional[str] = None
    user: VicePrincipalUserCreate


class VicePrincipalPersonRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VicePrincipalUserRead(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    role: UserRole
    school_id: Optional[UUID] = None
    person: Optional[VicePrincipalPersonRead] = None

    model_config = ConfigDict(from_attributes=True)


class VicePrincipalEmployeeRead(BaseModel):
    id: UUID
    employee_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VicePrincipalSchoolRead(BaseModel):
    id: UUID
    name: str
    school_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VicePrincipalRead(BaseModel):
    id: UUID
    school_id: UUID
    user_id: UUID
    employee_id: UUID
    created_at: datetime
    updated_at: datetime

    user: Optional[VicePrincipalUserRead] = None
    employee: Optional[VicePrincipalEmployeeRead] = None
    school: Optional[VicePrincipalSchoolRead] = None

    model_config = ConfigDict(from_attributes=True)