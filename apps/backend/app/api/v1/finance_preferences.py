from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceClient, User
from app.services.finance_preferences import client_reminders_enabled, set_client_reminders

router = APIRouter(prefix="/finance/preferences", tags=["finance-preferences"])


class ReminderPreferenceUpdate(BaseModel):
    enabled: bool


@router.get("/clients")
def list_client_preferences(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    clients = db.scalars(select(FinanceClient).order_by(FinanceClient.name.asc())).all()
    return {
        "items": [
            {"client_id": str(client.id), "reminders_enabled": client_reminders_enabled(db, client.id)}
            for client in clients
        ]
    }


@router.patch("/clients/{client_id}/reminders")
def update_client_reminder_preference(
    client_id: UUID,
    payload: ReminderPreferenceUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    set_client_reminders(db, client.id, payload.enabled, actor_user_id=current.id)
    db.commit()
    return {"client_id": str(client.id), "reminders_enabled": payload.enabled}
