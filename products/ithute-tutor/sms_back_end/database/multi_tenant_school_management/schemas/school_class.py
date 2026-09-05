from uuid import UUID

from pydantic import BaseModel


class SchoolClassCreate(BaseModel):
    school_id: UUID
    class_id: UUID
    capacity: int


class SchoolClassRead(BaseModel):
    id: UUID
    school_id: UUID
    class_id: UUID
    capacity: int