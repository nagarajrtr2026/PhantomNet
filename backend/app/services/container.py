from dataclasses import dataclass

from app.config import Settings
from app.context.store import ChromaContextStore
from app.database.dynamic_sql.engine import DynamicSqlEngine
from app.filesystem.virtual_fs import VirtualFilesystem
from app.services.llm import PhaseThreeLLMService
from app.sessions.manager import SessionManager
from app.telemetry.broker import EventBroker


@dataclass
class Services:
    settings: Settings
    sessions: SessionManager
    telemetry: EventBroker
    context: ChromaContextStore
    llm: PhaseThreeLLMService
    filesystem: VirtualFilesystem
    dynamic_sql: DynamicSqlEngine


def build_services(settings: Settings) -> Services:
    context = ChromaContextStore(settings)
    llm = PhaseThreeLLMService()
    sessions = SessionManager(max_sessions=settings.max_sessions)
    telemetry = EventBroker(settings)
    return Services(
        settings=settings,
        sessions=sessions,
        telemetry=telemetry,
        context=context,
        llm=llm,
        filesystem=VirtualFilesystem(
            context, llm, settings.max_file_bytes, sessions, telemetry
        ),
        dynamic_sql=DynamicSqlEngine(context, llm, settings.max_input_bytes),
    )
