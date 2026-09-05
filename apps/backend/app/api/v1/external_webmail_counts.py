from typing import Annotated

from fastapi import APIRouter, Cookie

from app.api.v1.external_webmail import EXTERNAL_COOKIE, _config, _failure
from app.services.external_webmail import (
    ExternalWebmailError,
    _imap,
    _list_folder_names,
)

router = APIRouter(prefix="/webmail/external", tags=["external-webmail-counts"])


def _uid_count(data) -> int:
    if not data or not data[0]:
        return 0
    raw = data[0]
    if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
    return len(str(raw).split())


@router.get("/folder-counts")
def exact_folder_counts(
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    """Return counts using the same selected-mailbox search path as messages.

    Some IMAP servers report stale STATUS(MESSAGES) values for special folders,
    especially Drafts. Selecting each folder read-only and searching its current
    UID set keeps the drawer aligned with what iMail can actually open.
    """
    config = _config(token)
    client = _imap(config)
    try:
        rows = []
        for name in _list_folder_names(client):
            status, _ = client.select(name, readonly=True)
            if status != "OK":
                rows.append({"name": name, "messages": 0, "unseen": 0})
                continue

            all_status, all_data = client.uid("search", None, "ALL")
            unseen_status, unseen_data = client.uid("search", None, "UNSEEN")
            total = _uid_count(all_data) if all_status == "OK" else 0
            unseen = _uid_count(unseen_data) if unseen_status == "OK" else 0
            rows.append({"name": name, "messages": total, "unseen": unseen})
        return {"items": rows}
    except ExternalWebmailError as exc:
        raise _failure(exc) from exc
    finally:
        try:
            client.logout()
        except Exception:
            pass
