from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from ws.connection_manager import socket_manager

router = APIRouter(prefix="/ws", tags=["Websocket Connection"])


from fastapi import WebSocket, WebSocketDisconnect
import json

@router.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    await socket_manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except Exception:
                continue

            if data.get("event") == "PING":
                await websocket.send_json({
                    "event": "PONG"
                })

    except WebSocketDisconnect:
        socket_manager.disconnect(websocket)

    except Exception:
        socket_manager.disconnect(websocket)