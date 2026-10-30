from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationRequest:
    session_id: str
    operation: str
    user_input: str
    context: tuple[str, ...] = ()
    path: str | None = None
    database: str | None = None
    user: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    content: str | None = None
    is_directory: bool = False
    children: tuple[tuple[str, bool], ...] = ()


class LLMUnavailableError(RuntimeError):
    pass


class LLMService(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...


class PhaseThreeLLMService:
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        raise LLMUnavailableError(
            "No LLM provider is implemented in Phase 2; connect Ollama in Phase 3."
        )
