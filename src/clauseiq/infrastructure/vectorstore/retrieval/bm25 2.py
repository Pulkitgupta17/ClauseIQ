"""BM25 (lexical) retrieval strategy.

A sparse, exact-term ranker over an in-memory ``rank-bm25`` index. Strong where
dense retrieval is weak: precise legal terminology and section numbers
("Section 23", "indemnify", "lock-in") that must match by the actual words.

The index is built once from a fixed set of chunks (the law corpus is small —
hundreds of chunks — so an in-memory index is appropriate). Use
:func:`build_bm25_from_store` to populate it from a vector store.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, ClassVar, TypeAlias

from clauseiq.domain.entities import Chunk, ScoredChunk
from clauseiq.domain.exceptions import RetrievalError
from clauseiq.domain.ports import VectorStore
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.infrastructure.vectorstore.retrieval.base import BaseRetriever

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi

Tokenizer: TypeAlias = Callable[[str], list[str]]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def default_tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric tokenizer (deterministic, dependency-free)."""
    return _TOKEN_RE.findall(text.lower())


class BM25Retriever(BaseRetriever):
    """Ranks a fixed chunk corpus by BM25 relevance to the query.

    Args:
        chunks: The corpus to index and rank.
        tokenizer: How to split text into terms. Injectable for testing/tuning.
    """

    name: ClassVar[str] = "bm25"

    def __init__(self, chunks: Sequence[Chunk], *, tokenizer: Tokenizer = default_tokenize) -> None:
        self._chunks = list(chunks)
        self._tokenizer = tokenizer
        self._index: BM25Okapi | None = None
        if self._chunks:
            from rank_bm25 import BM25Okapi

            self._index = BM25Okapi([tokenizer(chunk.text) for chunk in self._chunks])

    def _rank_sync(self, query: str, k: int) -> list[ScoredChunk]:
        if self._index is None:
            return []
        scores = self._index.get_scores(self._tokenizer(query))
        ranked = sorted(
            zip(self._chunks, scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
        # Keep only chunks with positive lexical overlap; zero-score docs are noise.
        return [
            ScoredChunk(chunk=chunk, score=float(score))
            for chunk, score in ranked[:k]
            if float(score) > 0.0
        ]

    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        if not query.strip():
            return Err(RetrievalError("empty_query"))
        try:
            results = await asyncio.to_thread(self._rank_sync, query, k)
        except Exception as exc:  # external boundary (index/runtime errors)
            return Err(RetrievalError("bm25_retrieval_failed", cause=exc))
        return Ok(results)


async def build_bm25_from_store(
    store: VectorStore, *, tokenizer: Tokenizer = default_tokenize
) -> BM25Retriever:
    """Build a :class:`BM25Retriever` from every chunk in ``store``."""
    chunks = await store.get_all()
    return BM25Retriever(chunks, tokenizer=tokenizer)


__all__ = ["BM25Retriever", "Tokenizer", "build_bm25_from_store", "default_tokenize"]
