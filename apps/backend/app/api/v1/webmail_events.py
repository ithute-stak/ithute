import asyncio
import json
import re
from typing import Annotated, AsyncIterator
from urllib.parse import urlsplit

import redis
from fastapi import APIRouter, Cookie, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.services.mail_events import MailEventStream, POLL_SECONDS
from app.services.webmail import WebmailError, session_credentials


router = APIRouter(prefix="/webmail/events", tags=["webmail-events"])
EVENT_ID_RE = re.compile(r"^(\$|[0-9]+-[0-9]+)$")


def _credentials(token: str | None) -> tuple[str, str]:
    try:
        return session_credentials(token or "")
    except WebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _event_cursor(value: str | None) -> str:
    requested = (value or "$").strip() or "$"
    return requested if EVENT_ID_RE.fullmatch(requested) else "$"


def _sse(event: dict) -> str:
    return "\n".join(
        [
            f"id: {event['id']}",
            f"event: {event['type']}",
            f"data: {json.dumps(event, separators=(',', ':'), ensure_ascii=False)}",
            "",
            "",
        ]
    )


def _allowed_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    expected = urlsplit(settings.frontend_url)
    actual = urlsplit(origin)
    return (
        actual.scheme.lower() == expected.scheme.lower()
        and actual.netloc.lower() == expected.netloc.lower()
    )


@router.get("/stream")
async def sse_stream(
    request: Request,
    token: Annotated[str | None, Cookie(alias=settings.webmail_session_cookie_name)] = None,
):
    address, password = await asyncio.to_thread(_credentials, token)
    last_id = _event_cursor(request.headers.get("last-event-id"))

    async def events() -> AsyncIterator[str]:
        stream = MailEventStream(address)
        cursor = last_id
        try:
            yield "event: ready\ndata: {\"type\":\"ready\"}\n\n"
            while not await request.is_disconnected():
                try:
                    rows = await stream.read(cursor, POLL_SECONDS * 1000)
                except redis.RedisError:
                    yield "event: degraded\ndata: {\"type\":\"degraded\",\"reason\":\"event-store-unavailable\"}\n\n"
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                if rows:
                    for event in rows:
                        cursor = event["id"]
                        yield _sse(event)
                    continue

                change = await stream.probe_mailbox(password)
                if change:
                    cursor = change["id"]
                    yield _sse(change)
                else:
                    yield ": keepalive\n\n"
        finally:
            await stream.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    if not _allowed_websocket_origin(websocket):
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get(settings.webmail_session_cookie_name)
    try:
        address, password = await asyncio.to_thread(session_credentials, token or "")
    except WebmailError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    stream = MailEventStream(address)
    cursor = _event_cursor(websocket.query_params.get("last_event_id"))
    try:
        await websocket.send_json({"type": "ready", "cursor": cursor})
        while True:
            try:
                rows = await stream.read(cursor, POLL_SECONDS * 1000)
            except redis.RedisError:
                await websocket.send_json({"type": "degraded", "reason": "event-store-unavailable"})
                await asyncio.sleep(POLL_SECONDS)
                continue
            if rows:
                for event in rows:
                    cursor = event["id"]
                    await websocket.send_json(event)
                continue

            change = await stream.probe_mailbox(password)
            if change:
                cursor = change["id"]
                await websocket.send_json(change)
            else:
                await websocket.send_json({"type": "heartbeat"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await stream.close()
