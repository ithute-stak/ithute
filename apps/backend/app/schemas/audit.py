from pydantic import BaseModel


class AuditOut(BaseModel):
    id: str
    tenant_id: str | None
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata: dict | None
    prev_hash: str | None = None
    event_hash: str | None = None
    created_at: str
