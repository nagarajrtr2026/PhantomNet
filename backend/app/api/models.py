from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class SessionCreateRequest(BaseModel):
    source_ip: IPvAnyAddress
    protocol: str = Field(min_length=1, max_length=32)
    source_port: int | None = Field(default=None, ge=1, le=65535)


class NetworkCaptureRequest(BaseModel):
    source_ip: IPvAnyAddress
    source_port: int | None = Field(default=None, ge=1, le=65535)
    destination: IPvAnyAddress | None = None
    destination_port: int = Field(ge=1, le=65535)
    protocol: str = Field(min_length=1, max_length=32)


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4096)


class SqlQueryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=16384)
    database: str | None = Field(default=None, max_length=128)
    user: str | None = Field(default=None, max_length=128)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    session_id: str
    source_ip: str
    source_port: int | None
    protocol: str
    started_at: datetime
    last_activity: datetime
    state: str
    event_ids: list[str]
