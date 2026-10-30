import logging

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.container import Services


logger = logging.getLogger("phantomnet.websocket")
router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket, after: str | None = None) -> None:
    services: Services = websocket.app.state.services
    try:
        replay, queue = await services.telemetry.subscribe(after)
    except ConnectionError:
        await websocket.close(code=1013, reason="WebSocket capacity reached")
        return

    await websocket.accept()
    try:
        for event in replay:
            await websocket.send_json(event)

        async def send_events() -> None:
            while True:
                await websocket.send_json(await queue.get())

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(send_events)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                task_group.cancel_scope.cancel()
    except Exception:
        logger.exception("Telemetry WebSocket client disconnected unexpectedly")
    finally:
        await services.telemetry.unsubscribe(queue)
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
