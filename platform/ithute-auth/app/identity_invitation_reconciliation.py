from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .identity_invitation_models import IdentityInvitation
from .identity_invitation_schemas import IdentityInvitationResponse
from .identity_invitations import _response
from .service_authorization import ServiceContext, require_managed_service_scope


router = APIRouter(prefix="/v1/platform/identity-invitations", tags=["trusted-identity-invitations"])


@router.get("/activated-sub/{user_id}", response_model=list[IdentityInvitationResponse])
def list_activated_invitations_for_subject(
    user_id: uuid.UUID,
    context: ServiceContext = Depends(require_managed_service_scope("identity.invite")),
    db: Session = Depends(get_db),
) -> list[IdentityInvitationResponse]:
    """Return only this source service's consumed invitations for one Auth subject."""

    invitations = db.scalars(
        select(IdentityInvitation)
        .where(
            IdentityInvitation.source_client_id == context.client_id,
            IdentityInvitation.user_id == user_id,
            IdentityInvitation.consumed_at.is_not(None),
            IdentityInvitation.status == "activated",
        )
        .order_by(IdentityInvitation.consumed_at.asc(), IdentityInvitation.id.asc())
    ).all()
    return [_response(db, invitation) for invitation in invitations]
