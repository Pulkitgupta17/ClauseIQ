"""Dense (semantic) retrieval strategy.

Embeds the query and asks the vector store for the nearest chunks by cosine
similarity. Strong at *meaning* — it matches paraphrases and synonyms that
lexical search misses (e.g. "you can't quit for a year" ~ a lock-in clause).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from clauseiq.domain.entities import ScoredChunk
from clauseiq.domain.exceptions import ClauseIQError, RetrievalError
from clauseiq.domain.ports import Embedder, VectorStore
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.infrastructure.vectorstore.retrieval.base import BaseRetriever


class DenseRetriever(BaseRetriever):
    """Retrieves chunks by embedding similarity via an :class:`Embedder` + store.

    Args:
        store: The vector store to query.
        embedder: Produces the query embedding.
        where: Optional metadata filter applied to every query (e.g. restrict to
            a given ``law_code``).
    """

    name: ClassVar[str] = "dense"

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        where: Mapping[str, str] | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._where = where

    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        if not query.strip():
            return Err(RetrievalError("empty_query"))
        try:
            embedding = await self._embedder.embed_query(query)
            results = await self._store.query(embedding, k, where=self._where)
        except ClauseIQError as exc:
            return Err(RetrievalError("dense_retrieval_failed", cause=exc))
        return Ok(results)


__all__ = ["DenseRetriever"]
