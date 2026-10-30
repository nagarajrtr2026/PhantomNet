from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SessionRecord(BaseModel):
    model_config = ConfigDict()

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    source_ip: str
    source_port: int | None = None
    protocol: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: str = "active"
    event_ids: list[str] = Field(default_factory=list)


class SessionNotFoundError(LookupError):
    pass


class SessionCapacityError(RuntimeError):
    pass


class SessionManager:
    def __init__(self, event_limit: int = 500, max_sessions: int = 5000) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._event_limit = event_limit
        self._max_sessions = max_sessions
        self._lock = RLock()

    def create(self, source_ip: str, protocol: str, source_port: int | None) -> SessionRecord:
        session = SessionRecord(
            source_ip=source_ip, protocol=protocol, source_port=source_port
        )
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                raise SessionCapacityError("Session capacity reached.")
            self._sessions[session.session_id] = session
        return session.model_copy(deep=True)

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            return session.model_copy(deep=True)

    def list(self) -> list[SessionRecord]:
        with self._lock:
            return [
                session.model_copy(deep=True)
                for session in sorted(
                    self._sessions.values(),
                    key=lambda item: item.last_activity,
                    reverse=True,
                )
            ]

    def record_event(self, session_id: str, event_id: str) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            session.last_activity = datetime.now(timezone.utc)
            session.state = "active"
            session.event_ids.append(event_id)
            del session.event_ids[:-self._event_limit]
            return session.model_copy(deep=True)

    def end(self, session_id: str) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            session.state = "ended"
            session.last_activity = datetime.now(timezone.utc)
            return session.model_copy(deep=True)
