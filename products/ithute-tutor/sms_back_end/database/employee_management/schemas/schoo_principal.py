from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict

from database.multi_tenant_school_management.schemas.user import UserRole


class PrincipalPersonCreate(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None


class PrincipalUserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.principal
    person: PrincipalPersonCreate


class PrincipalCreate(BaseModel):
    school_id: UUID
    employee_number: Optional[str] = None
    user: PrincipalUserCreate


class PrincipalPersonRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PrincipalUserRead(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    role: UserRole
    school_id: Optional[UUID] = None
    person: Optional[PrincipalPersonRead] = None

    model_config = ConfigDict(from_attributes=True)


class PrincipalEmployeeRead(BaseModel):
    id: UUID
    employee_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PrincipalSchoolRead(BaseModel):
    id: UUID
    name: str
    school_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PrincipalRead(BaseModel):
    id: UUID
    school_id: UUID
    user_id: UUID
    employee_id: UUID
    created_at: datetime
    updated_at: datetime

    user: Optional[PrincipalUserRead] = None
    employee: Optional[PrincipalEmployeeRead] = None
    school: Optional[PrincipalSchoolRead] = None

    model_config = ConfigDict(from_attributes=True)