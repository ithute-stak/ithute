from typing import List
from uuid import UUID
from pydantic import BaseModel

from .parent_student_light import StudentBasic
from .user import UserCreate, UserRead



class ParentBase(BaseModel):
    pass


class ParentCreate(BaseModel):
    user: UserCreate


class ParentRead(BaseModel):
    id: UUID
    user: UserRead

    model_config = {"from_attributes": True}


class ParentWithChildren(ParentRead):
    children: List[StudentBasic] = []