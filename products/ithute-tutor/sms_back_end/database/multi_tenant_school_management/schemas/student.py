from typing import Optional, List
from pydantic import BaseModel
from uuid import UUID

from .parent_student_light import ParentBasic
from .user import UserCreate, UserRead


class StudentBase(BaseModel):
    admission_number: str
    class_id: Optional[UUID]


class StudentCreate(StudentBase):
    user: UserCreate


class StudentRead(StudentBase):
    id: UUID
    user: UserRead
    model_config = {"from_attributes": True}


class StudentAdmissionNumberResponse(BaseModel):
    admission_number: str

class StudentWithParents(StudentRead):
    parents: List[ParentBasic] = []