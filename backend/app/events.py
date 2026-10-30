from datetime import datetime, timezone
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str | None = Field(default=None, alias="sessionId")


class HackerCommandEvent(EventBase):
    type: Literal["hacker_command"]
    command: str = Field(min_length=1, max_length=4096)
    source: str | None = Field(default=None, max_length=255)
    protocol: str | None = Field(default=None, max_length=32)


class NetworkEvent(EventBase):
    type: Literal["network_event"]
    action: str = Field(min_length=1, max_length=64)
    source: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = Field(default=None, max_length=32)


class FileAccessEvent(EventBase):
    type: Literal["file_access"]
    action: Literal["read", "list", "stat"]
    path: str = Field(min_length=1, max_length=1024)
    user: str | None = Field(default=None, max_length=128)


class SqlQueryEvent(EventBase):
    type: Literal["sql_query"]
    query: str = Field(min_length=1, max_length=16384)
    database: str | None = Field(default=None, max_length=128)
    user: str | None = Field(default=None, max_length=128)


class LlmResponseEvent(EventBase):
    type: Literal["llm_response"]
    input: str = Field(max_length=16384)
    response: str = Field(max_length=1048576)
    status: Literal["queued", "generating", "complete", "error"]
    streaming: bool = False
    model: str | None = Field(default=None, max_length=128)


class SessionUpdateEvent(EventBase):
    type: Literal["session_update"]
    status: Literal["started", "active", "ended"]
    source: str | None = Field(default=None, max_length=255)
    source_ip: str | None = Field(default=None, alias="sourceIp", max_length=64)
    duration_seconds: float | None = Field(
        default=None, alias="durationSeconds", ge=0
    )


class SecurityEvent(EventBase):
    type: Literal["security_event"]
    severity: Literal["low", "medium", "high", "critical"]
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2048)


TelemetryEvent = Annotated[
    Union[
        HackerCommandEvent,
        NetworkEvent,
        FileAccessEvent,
        SqlQueryEvent,
        LlmResponseEvent,
        SessionUpdateEvent,
        SecurityEvent,
    ],
    Field(discriminator="type"),
]


def event_payload(event: EventBase) -> dict[str, object]:
    return event.model_dump(mode="json", by_alias=True, exclude_none=True)
