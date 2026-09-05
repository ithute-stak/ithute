from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from database.multi_tenant_school_management.schemas.user import UserCreate, UserRead


class TeacherBase(BaseModel):
    school_id: UUID


class TeacherCreate(TeacherBase):
    user: UserCreate


class TeacherRead(TeacherBase):
    id: UUID
    user: UserRead

    model_config = {
        "from_attributes": True
    }