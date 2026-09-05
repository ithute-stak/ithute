from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import date
from typing import Optional, List

from database.multi_tenant_school_management.models.enum.gender import GenderEnum


class PersonBase(BaseModel):
    first_name: str
    last_name: str
    gender: GenderEnum
    date_of_birth: date
    nationality: str
    national_id: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    gender: Optional[GenderEnum]
    date_of_birth: Optional[date]
    nationality: Optional[str]
    national_id: Optional[str]


class PersonRead(PersonBase):
    id:UUID
    model_config = {
        "from_attributes": True
    }