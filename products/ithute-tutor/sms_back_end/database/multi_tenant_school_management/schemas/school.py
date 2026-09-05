from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from database.multi_tenant_school_management.models.enum.school_cat import SchoolCategory
from database.multi_tenant_school_management.schemas.school_contact import SchoolContactResponse
from database.multi_tenant_school_management.schemas.school_proprietor import SchoolProprietorResponse


class SchoolBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=120)
    school_code: Optional[str] = None
    registration_number: Optional[str] = None
    category: SchoolCategory
    logo_url: Optional[str] = None
    motto: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    timezone: str = "Africa/Maseru"
    currency: str = "LSL"
    locale: str = "en-LS"
    settings_json: dict[str, Any] = Field(default_factory=dict)


class SchoolCreate(SchoolBase):
    pass


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    school_code: Optional[str] = None
    registration_number: Optional[str] = None
    category: Optional[SchoolCategory] = None
    is_registered: Optional[bool] = None
    is_active: Optional[bool] = None
    certificate_number: Optional[str] = None
    logo_url: Optional[str] = None
    motto: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None
    settings_json: Optional[dict[str, Any]] = None


class SchoolResponse(SchoolBase):
    id: UUID
    is_registered: bool = False
    is_active: bool = True
    certificate_number: Optional[str] = None
    proprietor: Optional[SchoolProprietorResponse] = None
    contact_person: Optional[SchoolContactResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolMembershipResponse(BaseModel):
    id: UUID | None = None
    school_id: UUID
    role: str
    title: Optional[str] = None
    is_default: bool = False
    school: SchoolResponse

    model_config = ConfigDict(from_attributes=True)


class SchoolWorkspaceResponse(BaseModel):
    school: SchoolResponse
    role: str
    is_platform_admin: bool = False
    capabilities: list[str] = Field(default_factory=list)
