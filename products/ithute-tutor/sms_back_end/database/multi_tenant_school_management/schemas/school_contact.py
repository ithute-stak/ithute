# schemas/school_contact.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class SchoolContactBase(BaseModel):
    full_name: str
    designation: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: str


class SchoolContactCreate(SchoolContactBase):
    school_id: UUID


class SchoolContactResponse(SchoolContactBase):
    id: UUID
    school_id: UUID

    class Config:
        from_attributes = True