from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: UUID
    channel:str
    title: str
    message: str
    event: str
    created_at: datetime
    is_read: bool

    model_config = {
        "from_attributes": True
    }