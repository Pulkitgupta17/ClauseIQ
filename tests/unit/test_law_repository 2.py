"""Unit tests for the ChromaLawRepository (fakes — no real ChromaDB/model)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from clauseiq.domain.entities import Chunk, ScoredChunk
from clauseiq.domain.exceptions import RetrievalError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import LawCode
from clauseiq.infrastructure.repositories.law import (
    ChromaLawRepository,
    amendment_history_note,
)


def _law_chunk(section: str, *, title: str, text: str) -> Chunk:
    return Chunk(
        id=f"ICA_1872:s{section}::c0",
        text=text,
        metadata={
            "law_code": "ICA_1872",
            "section_number": section,
            "section_title": title,
            "section_text": text,
            "parent_section": f"ICA_1872:s{section}",
            "source_url": "http://example.test/ica.pdf",
            "effective_date": "1872-09-01",
            "source_fetched_at": "2026-06-25",
            "is_amendment_history_known": "false",
        },
    )


_CHUNKS = [
    _law_chunk(
        "23", title="What considerations and objects are lawful", text="... is void if unlawful."
    ),
    _law_chunk(
        "10", title="What agreements are contracts", text="All agreements are contracts ..."
    ),
]


class _FakeStore:
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = list(chunks)

    async def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None: ...

    async def query(
        self, embedding: Sequence[float], k: int, *, where: Mapping[str, str] | None = None
    ) -> list[ScoredChunk]:
        return []

    async def get_all(self, *, where: Mapping[str, str] | None = None) -> list[Chunk]:
        if where is None:
            return list(self._chunks)
        return [c for c in self._chunks if all(c.metadata.get(k) == v for k, v in where.items())]

    async def count(self) -> int:
        return len(self._chunks)


class _FakeRetriever:
    def __init__(self, result: Result[list[ScoredChunk], RetrievalError]) -> None:
        self._result = result

    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        return self._result


def _repo(result: Result[list[ScoredChunk], RetrievalError] | None = None) -> ChromaLawRepository:
    hits = result or Ok([ScoredChunk(chunk=_CHUNKS[0], score=0.03)])
    return ChromaLawRepository(_FakeStore(_CHUNKS), _FakeRetriever(hits))


async def test_search_delegates_to_retriever() -> None:
    result = await _repo().search("void contract", k=3)
    assert result.is_ok()
    assert result.unwrap()[0].chunk.metadata["section_number"] == "23"


async def test_search_wraps_retriever_error() -> None:
    repo = _repo(Err(RetrievalError("all_retrievers_failed")))
    result = await repo.search("x")
    assert result.is_err()
    assert result.unwrap_err().code == "RepositoryError"


async def test_get_section_builds_citation() -> None:
    result = await _repo().get_section(LawCode.ICA_1872, "23")
    assert result.is_ok()
    citation = result.unwrap()
    assert citation.reference == "Section 23, Indian Contract Act, 1872"
    assert citation.effective_date == date(1872, 9, 1)
    assert citation.last_amended is None
    assert citation.source_url == "http://example.test/ica.pdf"


async def test_get_section_missing_is_error() -> None:
    result = await _repo().get_section(LawCode.ICA_1872, "999")
    assert result.is_err()
    assert result.unwrap_err().code == "LawSectionNotFoundError"


async def test_count_returns_distinct_sections() -> None:
    assert await _repo().count() == 2


def test_to_citation_clamps_relevance_to_unit_interval() -> None:
    citation = ChromaLawRepository.to_citation(_CHUNKS[0], relevance_score=5.0)
    assert citation.relevance_score == 1.0


def test_amendment_history_note() -> None:
    from dataclasses import replace

    citation = ChromaLawRepository.to_citation(_CHUNKS[0])
    # last_amended is None -> caveat present.
    assert amendment_history_note(citation) is not None
    # last_amended known -> no caveat.
    assert amendment_history_note(replace(citation, last_amended=date(2020, 1, 1))) is None
