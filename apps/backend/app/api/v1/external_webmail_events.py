import asyncio
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.core.config import settings
from app.services.external_webmail import ExternalWebmailError, folder_counts, session_config
from app.services.mail_events import POLL_SECONDS

router = APIRouter(prefix="/webmail/external/events", tags=["external-webmail-events"])


def _allowed_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    expected = urlsplit(settings.frontend_url)
    actual = urlsplit(origin)
    return (
        actual.scheme.lower() == expected.scheme.lower()
        and actual.netloc.lower() == expected.netloc.lower()
    )


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    if not _allowed_origin(websocket):
        await websocket.close(code=4403)
        return

    token = websocket.cookies.get(EXTERNAL_COOKIE)
    try:
        config = await asyncio.to_thread(session_config, token or "")
    except ExternalWebmailError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    previous: str | None = None
    try:
        await websocket.send_json({"type": "ready", "provider": "external"})
        while True:
            try:
                counts = await asyncio.to_thread(folder_counts, config)
                snapshot = json.dumps(counts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                if previous is None:
                    previous = snapshot
                    await websocket.send_json({"type": "heartbeat"})
                elif snapshot != previous:
                    previous = snapshot
                    await websocket.send_json(
                        {
                            "type": "mailbox.changed",
                            "data": {"folders": counts},
                        }
                    )
                else:
                    await websocket.send_json({"type": "heartbeat"})
            except ExternalWebmailError:
                await websocket.send_json(
                    {"type": "degraded", "reason": "external-mailbox-unavailable"}
                )
            await asyncio.sleep(POLL_SECONDS)
    except (WebSocketDisconnect, RuntimeError):
        pass
