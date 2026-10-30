import asyncio
from collections import deque

from app.config import Settings
from app.events import EventBase, event_payload


class EventBroker:
    def __init__(self, settings: Settings) -> None:
        self._history: deque[dict[str, object]] = deque(
            maxlen=settings.event_history_size
        )
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._max_clients = settings.max_websocket_clients
        self._lock = asyncio.Lock()

    async def publish(self, event: EventBase) -> dict[str, object]:
        payload = event_payload(event)
        async with self._lock:
            self._history.append(payload)
            for queue in tuple(self._subscribers):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(payload)
        return payload

    async def snapshot(
        self, *, limit: int = 100, session_id: str | None = None
    ) -> list[dict[str, object]]:
        async with self._lock:
            events = list(self._history)
        if session_id:
            events = [event for event in events if event.get("sessionId") == session_id]
        return events[-limit:]

    async def subscribe(
        self, after_id: str | None = None
    ) -> tuple[list[dict[str, object]], asyncio.Queue[dict[str, object]]]:
        async with self._lock:
            if len(self._subscribers) >= self._max_clients:
                raise ConnectionError("WebSocket client capacity reached")
            history = list(self._history)
            start_index = 0
            if after_id:
                for index, event in enumerate(history):
                    if event.get("id") == after_id:
                        start_index = index + 1
                        break
            else:
                start_index = max(0, len(history) - 100)
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=256)
            self._subscribers.add(queue)
            return history[start_index:], queue

    async def unsubscribe(
        self, queue: asyncio.Queue[dict[str, object]]
    ) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    @property
    def connected_clients(self) -> int:
        return len(self._subscribers)
