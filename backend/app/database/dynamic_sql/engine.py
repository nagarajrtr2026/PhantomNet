import re

from app.context.store import ChromaContextStore
from app.services.llm import GenerationRequest, LLMService


SCHEMA_PATTERNS = (
    re.compile(r"\b(?:from|join|into|update|table)\s+([a-zA-Z_][\w.$]*)", re.IGNORECASE),
    re.compile(r"\buse\s+([a-zA-Z_][\w$]*)", re.IGNORECASE),
)
SENSITIVE_SQL = re.compile(
    r"\b(?:copy\s+.*\bprogram|pg_read_file|pg_write_file|load_file|xp_cmdshell|attach\s+database)\b",
    re.IGNORECASE,
)


class DynamicSqlEngine:
    def __init__(
        self,
        context: ChromaContextStore,
        llm: LLMService,
        max_input_bytes: int,
    ) -> None:
        self._context = context
        self._llm = llm
        self._max_input_bytes = max_input_bytes

    def normalize(self, query: str) -> str:
        normalized = query.strip()
        if not normalized:
            raise ValueError("SQL query must not be empty.")
        if "\x00" in query:
            raise ValueError("SQL query contains a null byte.")
        if len(normalized.encode("utf-8")) > self._max_input_bytes:
            raise ValueError("SQL query exceeds the configured size limit.")
        return normalized

    @staticmethod
    def extract_schema(query: str) -> list[str]:
        schemas: set[str] = set()
        for pattern in SCHEMA_PATTERNS:
            schemas.update(match.group(1) for match in pattern.finditer(query))
        return sorted(schemas)

    async def respond(
        self,
        session_id: str,
        query: str,
        *,
        database: str | None = None,
        user: str | None = None,
    ) -> str:
        schema = self.extract_schema(query)
        context = tuple(self._context.search(session_id, query, kind="sql_context", limit=5))
        if schema:
            context += tuple(self._context.search(session_id, " ".join(schema), limit=3))
        result = await self._llm.generate(
            GenerationRequest(
                session_id=session_id,
                operation="dynamic_sql",
                user_input=query,
                context=context,
                database=database,
                user=user,
            )
        )
        if result.content is None:
            raise ValueError("The LLM service returned no SQL response.")
        self._context.remember(session_id, "sql_context", query, result.content)
        return result.content

    @staticmethod
    def is_sensitive_probe(query: str) -> bool:
        return bool(SENSITIVE_SQL.search(query))
