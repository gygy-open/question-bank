import asyncio
from typing import Any, Dict, Optional

from app.core.vector_store import VectorStore


class KnowledgePointRetriever:
    """Gates knowledge-point vector search on availability and isolates by subject."""

    @staticmethod
    def available() -> bool:
        return VectorStore.is_available()

    @staticmethod
    async def retrieve(
        query: str, subject_id: Optional[int] = None, limit: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Return ChromaDB results scoped to subject_id, or None when unavailable."""
        if not KnowledgePointRetriever.available():
            return None
        return await asyncio.to_thread(
            VectorStore.search_similar,
            query=query,
            subject_id=subject_id,
            limit=limit,
        )
