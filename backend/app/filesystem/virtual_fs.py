from dataclasses import dataclass
from pathlib import PurePosixPath

from app.context.store import ChromaContextStore
from app.events import EventBase, FileAccessEvent, SecurityEvent
from app.services.llm import GenerationRequest, LLMService
from app.sessions.manager import SessionManager
from app.telemetry.broker import EventBroker


class InvalidVirtualPath(ValueError):
    pass


class VirtualPathNotFound(LookupError):
    pass


@dataclass(frozen=True)
class VirtualNode:
    path: str
    is_directory: bool
    content: str | None = None


def normalize_virtual_path(path: str) -> str:
    if "\x00" in path or "\\" in path or path.startswith("/"):
        raise InvalidVirtualPath("Only relative POSIX virtual paths are allowed.")
    parts = path.split("/")
    if any(part in (".", "..") for part in parts):
        raise InvalidVirtualPath("Path traversal is not allowed.")
    normalized = str(PurePosixPath(path)) if path else "."
    return "" if normalized == "." else normalized


class VirtualFilesystem:
    def __init__(
        self,
        context: ChromaContextStore,
        llm: LLMService,
        max_file_bytes: int,
        sessions: SessionManager,
        telemetry: EventBroker,
    ) -> None:
        self._context = context
        self._llm = llm
        self._max_file_bytes = max_file_bytes
        self._sessions = sessions
        self._telemetry = telemetry

    async def _record_access(self, session_id: str, action: str, path: str) -> None:
        await self._publish(
            FileAccessEvent(
                type="file_access",
                sessionId=session_id,
                action=action,
                path=path or "/",
            )
        )

    async def _publish(self, event: EventBase) -> None:
        payload = await self._telemetry.publish(event)
        session_id = payload.get("sessionId")
        if isinstance(session_id, str):
            session = self._sessions.record_event(session_id, str(payload["id"]))
            self._context.remember(
                session_id,
                "session_info",
                "session",
                session.model_dump_json(),
            )

    def _node(self, session_id: str, path: str) -> VirtualNode | None:
        record = self._context.get(session_id, "filesystem_node", path)
        if record is None:
            return None
        metadata = record["metadata"]
        content = None if metadata.get("is_directory") else str(record["document"])
        if metadata.get("generated") is False:
            content = None
        return VirtualNode(
            path=path,
            is_directory=bool(metadata.get("is_directory", False)),
            content=content,
        )

    async def _generate(self, session_id: str, path: str, operation: str) -> VirtualNode:
        context = tuple(self._context.search(session_id, path, limit=5))
        result = await self._llm.generate(
            GenerationRequest(
                session_id=session_id,
                operation=f"filesystem_{operation}",
                user_input=path,
                context=context,
                path=path,
            )
        )
        node = VirtualNode(path=path, is_directory=result.is_directory, content=result.content)
        if node.is_directory:
            self._context.remember(
                session_id, "filesystem_node", path, f"directory {path}", is_directory=True
            )
            for name, is_directory in result.children:
                if not name or name in (".", "..") or "/" in name or "\\" in name:
                    raise InvalidVirtualPath("Generated entry has an invalid name.")
                child_path = f"{path}/{name}" if path else name
                if is_directory:
                    self._context.remember(
                        session_id,
                        "filesystem_node",
                        child_path,
                        f"directory {child_path}",
                        is_directory=True,
                    )
                else:
                    self._context.remember(
                        session_id,
                        "filesystem_node",
                        child_path,
                        f"file {child_path}",
                        is_directory=False,
                        generated=False,
                    )
        elif node.content is not None:
            if len(node.content.encode("utf-8")) > self._max_file_bytes:
                raise ValueError("Generated file exceeds the configured size limit.")
            self._context.remember(
                session_id,
                "filesystem_node",
                path,
                node.content,
                is_directory=False,
                generated=True,
            )
        else:
            raise ValueError("The LLM service returned no content for a file.")
        return node

    async def list_directory(self, session_id: str, raw_path: str = "") -> list[str]:
        await self._record_access(session_id, "list", raw_path)
        try:
            path = normalize_virtual_path(raw_path)
        except InvalidVirtualPath:
            await self._publish(
                SecurityEvent(
                    type="security_event",
                    sessionId=session_id,
                    severity="high",
                    title="Virtual filesystem path traversal attempt",
                    description="A rejected path was requested from the isolated virtual filesystem.",
                )
            )
            raise
        if path:
            node = self._node(session_id, path)
            if node is None:
                node = await self._generate(session_id, path, "list")
            if not node.is_directory:
                raise NotADirectoryError(path)
        names: set[str] = set()
        for item in self._context.list_nodes(session_id, "filesystem_node"):
            metadata = item["metadata"]
            child_path = str(metadata.get("key", ""))
            parent = str(PurePosixPath(child_path).parent)
            if parent == ".":
                parent = ""
            if parent == path:
                names.add(PurePosixPath(child_path).name)
        return sorted(names)

    async def stat(self, session_id: str, raw_path: str) -> VirtualNode:
        await self._record_access(session_id, "stat", raw_path)
        try:
            path = normalize_virtual_path(raw_path)
        except InvalidVirtualPath:
            await self._publish(
                SecurityEvent(
                    type="security_event",
                    sessionId=session_id,
                    severity="high",
                    title="Virtual filesystem path traversal attempt",
                    description="A rejected path was requested from the isolated virtual filesystem.",
                )
            )
            raise
        if not path:
            return VirtualNode(path="", is_directory=True)
        node = self._node(session_id, path)
        if node is None:
            node = await self._generate(session_id, path, "stat")
        return node

    async def read_file(self, session_id: str, raw_path: str) -> str:
        await self._record_access(session_id, "read", raw_path)
        try:
            path = normalize_virtual_path(raw_path)
        except InvalidVirtualPath:
            await self._publish(
                SecurityEvent(
                    type="security_event",
                    sessionId=session_id,
                    severity="high",
                    title="Virtual filesystem path traversal attempt",
                    description="A rejected path was requested from the isolated virtual filesystem.",
                )
            )
            raise
        if not path:
            raise IsADirectoryError(path)
        node = self._node(session_id, path)
        if node is None or node.content is None:
            node = await self._generate(session_id, path, "read")
        if node.is_directory:
            raise IsADirectoryError(path)
        if node.content is None:
            raise VirtualPathNotFound(path)
        return node.content
