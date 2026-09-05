# schemas/school_proprietor.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class SchoolProprietorBase(BaseModel):
    full_name: str
    national_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: str


class SchoolProprietorCreate(SchoolProprietorBase):
    school_id: UUID


class SchoolProprietorResponse(SchoolProprietorBase):
    id: UUID
    school_id: UUID

    class Config:
        from_attributes = True