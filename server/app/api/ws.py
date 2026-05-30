"""WebSocket endpoint that streams live run events to the browser."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.runtime.bus import get_bus

router = APIRouter()


@router.websocket("/ws/events")
async def events(websocket: WebSocket):
    await websocket.accept()
    bus = get_bus()
    try:
        async for event in bus.subscribe():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except Exception:
        return
