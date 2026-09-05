from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict

from database.multi_tenant_school_management.schemas.user import UserRole


class PersonCreateForSchoolAdmin(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None


class UserCreateForSchoolAdmin(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.school_admin
    person: PersonCreateForSchoolAdmin


class SchoolAdminCreate(BaseModel):
    school_id: UUID
    employee_number: Optional[str] = None
    user: UserCreateForSchoolAdmin


class PersonReadForSchoolAdmin(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserReadForSchoolAdmin(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    role: UserRole
    school_id: Optional[UUID] = None
    person: Optional[PersonReadForSchoolAdmin] = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeReadForSchoolAdmin(BaseModel):
    id: UUID
    employee_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolMiniRead(BaseModel):
    id: UUID
    name: str
    school_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolAdminRead(BaseModel):
    id: UUID
    school_id: UUID
    user_id: UUID
    employee_id: UUID
    created_at: datetime
    updated_at: datetime

    user: Optional[UserReadForSchoolAdmin] = None
    employee: Optional[EmployeeReadForSchoolAdmin] = None
    school: Optional[SchoolMiniRead] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolAdminDashboardKpi(BaseModel):
    students: int
    teachers: int
    classes: int
    grades: int
    employees: int
    payments_count: int
    total_collected: float
    payroll_total: float
    payroll_paid: float
    payroll_unpaid: float


class FinanceSummary(BaseModel):
    total_collected: float
    payments_count: int
    today_collections: float


class PayrollSummary(BaseModel):
    total_payroll: float
    paid: float
    unpaid: float
    partial: float