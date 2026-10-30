import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_services
from app.api.models import (
    CommandRequest,
    NetworkCaptureRequest,
    SessionCreateRequest,
    SessionResponse,
    SqlQueryRequest,
)
from app.events import (
    EventBase,
    HackerCommandEvent,
    LlmResponseEvent,
    NetworkEvent,
    SecurityEvent,
    SessionUpdateEvent,
    SqlQueryEvent,
)
from app.network.interceptor.adapter import normalize_connection
from app.services.container import Services
from app.services.llm import GenerationRequest, LLMUnavailableError
from app.sessions.manager import SessionCapacityError, SessionNotFoundError


logger = logging.getLogger("phantomnet.security")
router = APIRouter(prefix="/api")
ServiceDependency = Annotated[Services, Depends(get_services)]


async def publish(services: Services, event: EventBase) -> dict[str, object]:
    payload = await services.telemetry.publish(event)
    session_id = payload.get("sessionId")
    if isinstance(session_id, str):
        try:
            session = services.sessions.record_event(session_id, str(payload["id"]))
            services.context.remember(
                session_id,
                "session_info",
                "session",
                session.model_dump_json(),
            )
        except SessionNotFoundError:
            logger.warning("Event referenced an unknown session: %s", session_id)
    return payload


async def log_llm_unavailable(
    services: Services, session_id: str, user_input: str
) -> None:
    await publish(
        services,
        LlmResponseEvent(
            type="llm_response",
            sessionId=session_id,
            input=user_input,
            response="",
            status="error",
        ),
    )


def require_session(services: Services, session_id: str):
    try:
        return services.sessions.get(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Session not found.") from error


def require_active_session(services: Services, session_id: str):
    session = require_session(services, session_id)
    if session.state != "active":
        raise HTTPException(status_code=409, detail="Session is no longer active.")
    return session


@router.get("/health")
async def health(services: ServiceDependency) -> dict[str, object]:
    return {
        "status": "ok",
        "service": "phantomnet-backend",
        "websocket_clients": services.telemetry.connected_clients,
        "active_sessions": sum(session.state == "active" for session in services.sessions.list()),
        "context_store": "chroma",
        "llm_provider": "not_configured_phase_2",
    }


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreateRequest, services: ServiceDependency):
    protocol = body.protocol.casefold()
    if protocol not in {"ssh", "postgresql", "mysql"}:
        raise HTTPException(status_code=422, detail="Unsupported ingress protocol.")
    try:
        session = services.sessions.create(str(body.source_ip), protocol, body.source_port)
    except SessionCapacityError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await publish(
        services,
        SessionUpdateEvent(
            type="session_update",
            sessionId=session.session_id,
            status="started",
            source=str(body.source_ip),
            sourceIp=str(body.source_ip),
        ),
    )
    return session


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    services: ServiceDependency,
    active_only: bool = Query(default=False, alias="activeOnly"),
):
    sessions = services.sessions.list()
    return [session for session in sessions if not active_only or session.state == "active"]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def session_detail(session_id: str, services: ServiceDependency):
    return require_session(services, session_id)


@router.post("/network/intercept", status_code=status.HTTP_202_ACCEPTED)
async def capture_connection(body: NetworkCaptureRequest, services: ServiceDependency):
    try:
        connection = normalize_connection(
            str(body.source_ip),
            body.source_port,
            str(body.destination) if body.destination else None,
            body.destination_port,
            body.protocol,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        session = services.sessions.create(
            connection.source_ip, connection.protocol, connection.source_port
        )
    except SessionCapacityError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await publish(
        services,
        SessionUpdateEvent(
            type="session_update",
            sessionId=session.session_id,
            status="started",
            source=connection.source_ip,
            sourceIp=connection.source_ip,
        ),
    )
    payload = await publish(
        services,
        NetworkEvent(
            type="network_event",
            sessionId=session.session_id,
            action="connection_observed",
            source=connection.source_ip,
            destination=connection.destination,
            port=connection.destination_port,
            protocol=connection.protocol,
        ),
    )
    logger.info(
        "Captured %s ingress from %s in session %s",
        connection.protocol,
        connection.source_ip,
        session.session_id,
    )
    return {"session": session, "event": payload}


@router.post("/sessions/{session_id}/commands", status_code=status.HTTP_202_ACCEPTED)
async def capture_command(
    session_id: str, body: CommandRequest, services: ServiceDependency
):
    session = require_active_session(services, session_id)
    event = HackerCommandEvent(
        type="hacker_command",
        sessionId=session_id,
        command=body.command,
        source=session.source_ip,
        protocol=session.protocol,
    )
    await publish(services, event)
    logger.warning("Command captured but never executed (session=%s)", session_id)
    services.context.remember(
        session_id, "attacker_request", event.id, body.command, protocol=session.protocol
    )
    try:
        context = tuple(services.context.search(session_id, body.command, limit=5))
        await services.llm.generate(
            GenerationRequest(
                session_id=session_id,
                operation="ssh_command",
                user_input=body.command,
                context=context,
            )
        )
    except LLMUnavailableError:
        await log_llm_unavailable(services, session_id, body.command)
        raise HTTPException(
            status_code=503, detail="LLM response generation is not configured in Phase 2."
        ) from None
    return {"accepted": True}


@router.get("/telemetry/events")
async def telemetry_events(
    services: ServiceDependency,
    limit: int = Query(default=100, ge=1, le=1000),
    session_id: str | None = Query(default=None, alias="sessionId", max_length=64),
):
    return await services.telemetry.snapshot(limit=limit, session_id=session_id)


@router.get("/filesystem/activity")
async def filesystem_activity(
    services: ServiceDependency,
    session_id: str | None = Query(default=None, alias="sessionId", max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
):
    events = await services.telemetry.snapshot(limit=1000, session_id=session_id)
    return [event for event in events if event["type"] == "file_access"][-limit:]


@router.get("/filesystem/{session_id}/list")
async def filesystem_list(
    session_id: str,
    services: ServiceDependency,
    path: str = Query(default="", max_length=1024),
):
    require_active_session(services, session_id)
    try:
        entries = await services.filesystem.list_directory(session_id, path)
    except LLMUnavailableError:
        await log_llm_unavailable(services, session_id, path or "/")
        raise HTTPException(
            status_code=503, detail="Directory generation is not configured in Phase 2."
        ) from None
    except NotADirectoryError as error:
        raise HTTPException(status_code=404, detail="Virtual directory not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"path": path or "/", "entries": entries}


@router.get("/filesystem/{session_id}/stat")
async def filesystem_stat(
    session_id: str,
    services: ServiceDependency,
    path: str = Query(default="", max_length=1024),
):
    require_active_session(services, session_id)
    try:
        node = await services.filesystem.stat(session_id, path)
    except LLMUnavailableError:
        await log_llm_unavailable(services, session_id, path)
        raise HTTPException(
            status_code=503, detail="Metadata generation is not configured in Phase 2."
        ) from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"path": path or "/", "type": "directory" if node.is_directory else "file"}


@router.get("/filesystem/{session_id}/read")
async def filesystem_read(
    session_id: str,
    services: ServiceDependency,
    path: str = Query(min_length=1, max_length=1024),
):
    require_active_session(services, session_id)
    try:
        return {"path": path, "content": await services.filesystem.read_file(session_id, path)}
    except IsADirectoryError as error:
        raise HTTPException(status_code=400, detail="Path is a virtual directory.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LLMUnavailableError:
        await log_llm_unavailable(services, session_id, path)
        raise HTTPException(
            status_code=503, detail="File generation is not configured in Phase 2."
        ) from None


@router.get("/sql/activity")
async def sql_activity(
    services: ServiceDependency,
    session_id: str | None = Query(default=None, alias="sessionId", max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
):
    events = await services.telemetry.snapshot(limit=1000, session_id=session_id)
    return [event for event in events if event["type"] == "sql_query"][-limit:]


@router.post("/sql/query")
async def sql_query(body: SqlQueryRequest, services: ServiceDependency):
    require_active_session(services, body.session_id)
    try:
        query = services.dynamic_sql.normalize(body.query)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    sql_event = SqlQueryEvent(
        type="sql_query",
        sessionId=body.session_id,
        query=query,
        database=body.database,
        user=body.user,
    )
    await publish(services, sql_event)
    services.context.remember(
        body.session_id, "attacker_request", sql_event.id, query, protocol="sql"
    )
    logger.info("Captured SQL request in isolated session %s", body.session_id)
    if services.dynamic_sql.is_sensitive_probe(query):
        await publish(
            services,
            SecurityEvent(
                type="security_event",
                sessionId=body.session_id,
                severity="medium",
                title="Sensitive SQL capability probe",
                description="Potentially sensitive SQL syntax was observed and was not executed.",
            ),
        )
    try:
        response = await services.dynamic_sql.respond(
            body.session_id, query, database=body.database, user=body.user
        )
    except LLMUnavailableError:
        await log_llm_unavailable(services, body.session_id, query)
        raise HTTPException(
            status_code=503, detail="Synthetic SQL generation is not configured in Phase 2."
        ) from None
    return {"response": response, "schema": services.dynamic_sql.extract_schema(query)}


@router.get("/security/status")
async def security_status(services: ServiceDependency):
    from app.filesystem.fuse.adapter import FUSE_AVAILABLE

    return {
        "status": "operational",
        "host_command_execution": False,
        "host_filesystem_access": False,
        "production_database_connections": False,
        "network_capture": "manual_ingress_only",
        "network_capture_enabled": services.settings.network_capture_enabled,
        "fuse": "available_not_mounted" if FUSE_AVAILABLE else "unavailable_on_this_platform",
        "context_store": "chroma",
        "llm_generation": "not_implemented_phase_2",
        "websocket_clients": services.telemetry.connected_clients,
    }


@router.get("/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    services: ServiceDependency,
    limit: int = Query(default=100, ge=1, le=1000),
):
    require_session(services, session_id)
    return await services.telemetry.snapshot(limit=limit, session_id=session_id)


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, services: ServiceDependency):
    session = require_session(services, session_id)
    duration = (datetime.now(timezone.utc) - session.started_at).total_seconds()
    await publish(
        services,
        SessionUpdateEvent(
            type="session_update",
            sessionId=session_id,
            status="ended",
            source=session.source_ip,
            sourceIp=session.source_ip,
            durationSeconds=duration,
        ),
    )
    return services.sessions.end(session_id)
