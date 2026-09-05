
from pydantic import BaseModel
from uuid import UUID

class ParentBasic(BaseModel):
    id: UUID

    model_config = {"from_attributes": True}
class StudentBasic(BaseModel):
    id: UUID
    admission_number: str

    model_config = {"from_attributes": True}