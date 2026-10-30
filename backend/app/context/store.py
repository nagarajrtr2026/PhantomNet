import hashlib
import re
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings


def _embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"[\w.-]+", text.casefold())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % dimensions
        vector[index] += 1.0 if value & (1 << 8) else -1.0
    magnitude = sum(component * component for component in vector) ** 0.5
    return [component / magnitude for component in vector] if magnitude else vector


class ChromaContextStore:
    def __init__(self, settings: Settings) -> None:
        client = chromadb.PersistentClient(
            path=settings.chroma_persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def remember(
        self, session_id: str, kind: str, key: str, document: str, **metadata: str | int | float | bool
    ) -> None:
        record_id = hashlib.sha256(
            f"{session_id}\0{kind}\0{key}".encode("utf-8")
        ).hexdigest()
        self._collection.upsert(
            ids=[record_id],
            documents=[document],
            embeddings=[_embedding(document)],
            metadatas=[
                {
                    "session_id": session_id,
                    "kind": kind,
                    "key": key,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    **metadata,
                }
            ],
        )

    def get(self, session_id: str, kind: str, key: str) -> dict[str, object] | None:
        record_id = hashlib.sha256(
            f"{session_id}\0{kind}\0{key}".encode("utf-8")
        ).hexdigest()
        result = self._collection.get(
            ids=[record_id], include=["documents", "metadatas"]
        )
        if not result["ids"]:
            return None
        return {
            "document": result["documents"][0],
            "metadata": result["metadatas"][0] or {},
        }

    def list_nodes(self, session_id: str, kind: str) -> list[dict[str, object]]:
        result = self._collection.get(
            where={"$and": [{"session_id": session_id}, {"kind": kind}]},
            include=["documents", "metadatas"],
        )
        return [
            {"document": document, "metadata": metadata or {}}
            for document, metadata in zip(result["documents"], result["metadatas"])
        ]

    def search(
        self, session_id: str, query: str, *, kind: str | None = None, limit: int = 5
    ) -> list[str]:
        where: dict[str, object] = {"session_id": session_id}
        if kind:
            where = {"$and": [{"session_id": session_id}, {"kind": kind}]}
        result = self._collection.query(
            query_embeddings=[_embedding(query)],
            n_results=limit,
            where=where,
            include=["documents"],
        )
        return result["documents"][0] if result["documents"] else []
