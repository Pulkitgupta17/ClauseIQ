"""Ports — the abstract interfaces the domain depends on.

These are :class:`~typing.Protocol` classes (structural typing): the domain and
application layers depend only on these shapes, while concrete adapters live in
:mod:`clauseiq.infrastructure`. This is the Dependency Inversion Principle in
practice — inner layers define the interface, outer layers implement it — and is
what keeps the dependency rule intact.

All I/O-bearing methods are ``async`` per the project's async-first rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from clauseiq.domain.entities import Chunk, Citation, ScoredChunk
from clauseiq.domain.exceptions import RepositoryError, RetrievalError
from clauseiq.domain.result import Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode


@runtime_checkable
class Embedder(Protocol):
    """Turns text into dense vectors (e.g. all-MiniLM-L6-v2)."""

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents for indexing."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """A persistent store of embedded chunks supporting similarity search."""

    async def add(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Upsert ``chunks`` with their precomputed ``embeddings``."""
        ...

    async def query(
        self,
        embedding: Sequence[float],
        k: int,
        *,
        where: Mapping[str, str] | None = None,
    ) -> list[ScoredChunk]:
        """Return the ``k`` nearest chunks, optionally filtered by metadata."""
        ...

    async def get_all(
        self,
        *,
        where: Mapping[str, str] | None = None,
    ) -> list[Chunk]:
        """Return all stored chunks (used to build sparse indexes like BM25)."""
        ...

    async def count(self) -> int:
        """Return the number of chunks currently stored."""
        ...


@runtime_checkable
class Retriever(Protocol):
    """A retrieval strategy (dense, sparse, or hybrid)."""

    async def retrieve(
        self,
        query: str,
        k: int = 5,
    ) -> Result[list[ScoredChunk], RetrievalError]:
        """Return up to ``k`` chunks relevant to ``query`` (or an error)."""
        ...


@runtime_checkable
class LawRepository(Protocol):
    """Read access to the corpus of Indian statutory sections."""

    async def search(
        self,
        query: str,
        k: int = 5,
        *,
        jurisdiction: Jurisdiction | None = None,
    ) -> Result[list[ScoredChunk], RepositoryError]:
        """Hybrid-search the law corpus, optionally scoped to a jurisdiction."""
        ...

    async def get_section(
        self,
        law_code: LawCode,
        section_number: str,
    ) -> Result[Citation, RepositoryError]:
        """Fetch a single statutory section as a :class:`Citation`."""
        ...

    async def count(self) -> int:
        """Return the number of statutory sections in the corpus."""
        ...


__all__ = ["Embedder", "LawRepository", "Retriever", "VectorStore"]
