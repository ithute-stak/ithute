from typing import Annotated

from fastapi import APIRouter, Cookie

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.api.v1.external_webmail_rich import RichDraft, RichSend, save_rich_draft, send_rich

router = APIRouter(prefix="/webmail/external", tags=["external-webmail-rich"])


@router.post("/send", status_code=202)
def send_alias(
    payload: RichSend,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    return send_rich(payload, token)


@router.post("/drafts", status_code=201)
def draft_alias(
    payload: RichDraft,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    return save_rich_draft(payload, token)
