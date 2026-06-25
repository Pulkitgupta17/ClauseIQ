"""Unit tests for the domain ports (Protocols).

Protocols carry no behaviour, so these tests verify the *contract*: a conforming
object satisfies the structural type (``runtime_checkable`` ``isinstance``), and
a non-conforming one does not. This also ensures the module imports cleanly and
its signatures stay in sync with the entities they reference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from clauseiq.domain.entities import Chunk, Citation, ScoredChunk
from clauseiq.domain.exceptions import RepositoryError, RetrievalError
from clauseiq.domain.ports import Embedder, LawRepository, Retriever, VectorStore
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode


class _FakeEmbedder:
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, float(len(text))]


class _FakeRetriever:
    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        if not query:
            return Err(RetrievalError("empty_query"))
        return Ok([ScoredChunk(chunk=Chunk(id="c1", text=query), score=1.0)][:k])


class _FakeVectorStore:
    async def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        return None

    async def query(
        self, embedding: Sequence[float], k: int, *, where: Mapping[str, str] | None = None
    ) -> list[ScoredChunk]:
        return []

    async def get_all(self, *, where: Mapping[str, str] | None = None) -> list[Chunk]:
        return []

    async def count(self) -> int:
        return 0


class _FakeLawRepository:
    async def search(
        self, query: str, k: int = 5, *, jurisdiction: Jurisdiction | None = None
    ) -> Result[list[ScoredChunk], RepositoryError]:
        return Ok([])

    async def get_section(
        self, law_code: LawCode, section_number: str
    ) -> Result[Citation, RepositoryError]:
        return Err(RepositoryError("not_found"))

    async def count(self) -> int:
        return 0


def test_conforming_objects_satisfy_protocols() -> None:
    assert isinstance(_FakeEmbedder(), Embedder)
    assert isinstance(_FakeRetriever(), Retriever)
    assert isinstance(_FakeVectorStore(), VectorStore)
    assert isinstance(_FakeLawRepository(), LawRepository)


def test_non_conforming_object_is_rejected() -> None:
    assert not isinstance(object(), Retriever)
    assert not isinstance(_FakeEmbedder(), VectorStore)


async def test_fake_retriever_returns_result() -> None:
    retriever: Retriever = _FakeRetriever()
    ok = await retriever.retrieve("void contract", k=1)
    assert ok.is_ok()
    err = await retriever.retrieve("")
    assert err.is_err()
