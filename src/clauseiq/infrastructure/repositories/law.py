"""Law repository — read access to the Indian statutory corpus.

Implements the domain :class:`~clauseiq.domain.ports.LawRepository` port over a
ChromaDB-backed vector store plus a hybrid retriever. ``search`` returns ranked
chunks; ``get_section`` returns a single section as a :class:`Citation`.

Amendment caveat (must be honoured downstream): a section's ``last_amended`` is
``None`` whenever the corpus could not derive it, and the corpus does not track
amendment history. :func:`amendment_history_note` returns the user-facing string
to display (e.g. on the frontend) so we never imply a citation reflects the
current, amended law.
"""

from __future__ import annotations

from datetime import date

from clauseiq.domain.entities import Chunk, Citation, ScoredChunk
from clauseiq.domain.exceptions import (
    LawSectionNotFoundError,
    RepositoryError,
    VectorStoreError,
)
from clauseiq.domain.ports import Retriever, VectorStore
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode
from clauseiq.logging_config import get_logger

log = get_logger(__name__)


def amendment_history_note(citation: Citation) -> str | None:
    """User-facing caveat for a citation, or ``None`` if an amendment date exists.

    The corpus does not track amendment history; when ``last_amended`` is unknown
    this returns a message the UI should show so users verify current law.
    """
    if citation.last_amended is not None:
        return None
    return "Amendment history not tracked — verify current law for time-sensitive matters."


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _law_code(value: str | None) -> LawCode:
    try:
        return LawCode(value) if value else LawCode.OTHER
    except ValueError:
        return LawCode.OTHER


class ChromaLawRepository:
    """ChromaDB-backed implementation of the ``LawRepository`` port."""

    def __init__(self, store: VectorStore, retriever: Retriever) -> None:
        self._store = store
        self._retriever = retriever

    async def search(
        self,
        query: str,
        k: int = 5,
        *,
        jurisdiction: Jurisdiction | None = None,
    ) -> Result[list[ScoredChunk], RepositoryError]:
        """Hybrid-search the law corpus (jurisdiction is reserved for future use)."""
        result = await self._retriever.retrieve(query, k)
        if result.is_err():
            return Err(RepositoryError("law_search_failed", cause=result.unwrap_err()))
        return Ok(result.unwrap())

    async def get_section(
        self,
        law_code: LawCode,
        section_number: str,
    ) -> Result[Citation, RepositoryError]:
        """Fetch a single statutory section as a :class:`Citation`."""
        section_id = f"{law_code.value}:s{section_number}"
        try:
            chunks = await self._store.get_all(where={"parent_section": section_id})
        except VectorStoreError as exc:
            return Err(RepositoryError("get_section_failed", cause=exc, section=section_id))
        if not chunks:
            return Err(
                LawSectionNotFoundError(
                    "section_not_found", law_code=law_code.value, section=section_number
                )
            )
        return Ok(self.to_citation(chunks[0]))

    async def count(self) -> int:
        """Return the number of distinct statutory sections stored."""
        chunks = await self._store.get_all()
        return len({chunk.metadata.get("parent_section", chunk.id) for chunk in chunks})

    @classmethod
    def to_citation(cls, chunk: Chunk, *, relevance_score: float | None = None) -> Citation:
        """Reconstruct a :class:`Citation` from a stored chunk's metadata."""
        metadata = chunk.metadata
        clamped = max(0.0, min(1.0, relevance_score)) if relevance_score is not None else None
        return Citation(
            law_code=_law_code(metadata.get("law_code")),
            section_number=metadata.get("section_number") or "?",
            section_title=metadata.get("section_title") or "Untitled",
            snippet=metadata.get("section_text") or chunk.text,
            source_url=metadata.get("source_url") or None,
            effective_date=_parse_date(metadata.get("effective_date")),
            last_amended=_parse_date(metadata.get("last_amended")),
            source_fetched_at=_parse_date(metadata.get("source_fetched_at")),
            relevance_score=clamped,
        )

    def citation_from_scored(self, scored: ScoredChunk) -> Citation:
        """Build a citation from a search hit, carrying its relevance score."""
        return self.to_citation(scored.chunk, relevance_score=scored.score)


async def build_law_repository() -> ChromaLawRepository:
    """Wire a hybrid law repository from settings (embedded ChromaDB).

    The BM25 index is built from the stored corpus when this is called; in a
    long-lived process it would be built once at startup and cached.
    """
    from clauseiq.infrastructure.vectorstore.chroma import build_law_vector_store
    from clauseiq.infrastructure.vectorstore.embedder import SentenceTransformerEmbedder
    from clauseiq.infrastructure.vectorstore.retrieval.bm25 import build_bm25_from_store
    from clauseiq.infrastructure.vectorstore.retrieval.dense import DenseRetriever
    from clauseiq.infrastructure.vectorstore.retrieval.hybrid import HybridRetriever

    store = build_law_vector_store()
    embedder = SentenceTransformerEmbedder()
    bm25 = await build_bm25_from_store(store)
    dense = DenseRetriever(store, embedder)
    hybrid = HybridRetriever([dense, bm25])
    return ChromaLawRepository(store, hybrid)


__all__ = ["ChromaLawRepository", "amendment_history_note", "build_law_repository"]
