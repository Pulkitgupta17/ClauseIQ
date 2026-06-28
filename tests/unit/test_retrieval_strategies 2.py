"""Unit tests for the retrieval strategies (dense, BM25, hybrid RRF).

All I/O is faked: no real embedding model or ChromaDB. BM25 uses the real
``rank-bm25`` index over a tiny in-memory corpus.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from clauseiq.domain.entities import Chunk, ScoredChunk
from clauseiq.domain.exceptions import RetrievalError, VectorStoreError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.infrastructure.vectorstore.retrieval.base import BaseRetriever
from clauseiq.infrastructure.vectorstore.retrieval.bm25 import BM25Retriever
from clauseiq.infrastructure.vectorstore.retrieval.dense import DenseRetriever
from clauseiq.infrastructure.vectorstore.retrieval.hybrid import HybridRetriever


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(id=chunk_id, text=text, metadata={"parent_section": chunk_id})


CORPUS = [
    _chunk(
        "s23", "The consideration or object of an agreement is unlawful and the agreement is void"
    ),
    _chunk(
        "s10",
        "All agreements are contracts if made by free consent of parties competent to contract",
    ),
    _chunk(
        "s27",
        "Every agreement by which anyone is restrained from exercising a lawful profession is void",
    ),
]


# --- Fakes -------------------------------------------------------------------


class _FakeEmbedder:
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


class _FakeStore:
    def __init__(self, results: list[ScoredChunk] | None = None, *, fail: bool = False) -> None:
        self._results = results or []
        self._fail = fail

    async def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        return None

    async def query(
        self, embedding: Sequence[float], k: int, *, where: Mapping[str, str] | None = None
    ) -> list[ScoredChunk]:
        if self._fail:
            raise VectorStoreError("boom")
        return self._results[:k]

    async def get_all(self, *, where: Mapping[str, str] | None = None) -> list[Chunk]:
        return list(CORPUS)

    async def count(self) -> int:
        return len(self._results)


class _StaticRetriever(BaseRetriever):
    """Returns a fixed result, for testing the fuser in isolation."""

    def __init__(self, name: str, result: Result[list[ScoredChunk], RetrievalError]) -> None:
        self.name = name
        self._result = result

    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        return self._result


# --- Dense -------------------------------------------------------------------


async def test_dense_returns_store_results() -> None:
    expected = [ScoredChunk(chunk=CORPUS[0], score=0.9)]
    retriever = DenseRetriever(_FakeStore(expected), _FakeEmbedder())
    result = await retriever.retrieve("what makes a contract void", k=5)
    assert result == Ok(expected)


async def test_dense_empty_query_is_error() -> None:
    result = await DenseRetriever(_FakeStore(), _FakeEmbedder()).retrieve("   ")
    assert result.is_err()


async def test_dense_wraps_store_failure_as_retrieval_error() -> None:
    retriever = DenseRetriever(_FakeStore(fail=True), _FakeEmbedder())
    result = await retriever.retrieve("void contract")
    assert result.is_err()
    assert result.unwrap_err().code == "RetrievalError"


# --- BM25 --------------------------------------------------------------------


async def test_bm25_ranks_exact_terms_first() -> None:
    retriever = BM25Retriever(CORPUS)
    result = await retriever.retrieve("agreement restrained from lawful profession is void", k=3)
    assert result.is_ok()
    top = result.unwrap()
    assert top, "expected at least one lexical match"
    assert top[0].chunk.id == "s27"


async def test_bm25_empty_corpus_returns_empty_ok() -> None:
    result = await BM25Retriever([]).retrieve("anything")
    assert result == Ok([])


async def test_bm25_empty_query_is_error() -> None:
    assert (await BM25Retriever(CORPUS).retrieve("")).is_err()


async def test_bm25_drops_zero_overlap_documents() -> None:
    result = await BM25Retriever(CORPUS).retrieve("xyzzy nonexistent term", k=3)
    assert result == Ok([])


# --- Hybrid (RRF) ------------------------------------------------------------


def _scored(ids: list[str]) -> list[ScoredChunk]:
    by_id = {c.id: c for c in CORPUS}
    return [ScoredChunk(chunk=by_id[i], score=1.0) for i in ids]


async def test_hybrid_requires_at_least_one_retriever() -> None:
    with pytest.raises(ValueError, match="at least one"):
        HybridRetriever([])


async def test_hybrid_rrf_fuses_and_orders_by_rank() -> None:
    dense = _StaticRetriever("dense", Ok(_scored(["s23", "s10", "s27"])))
    lexical = _StaticRetriever("bm25", Ok(_scored(["s10", "s23"])))
    fused = await HybridRetriever([dense, lexical], rrf_k=60).retrieve("q", k=3)
    assert fused.is_ok()
    ids = [s.chunk.id for s in fused.unwrap()]
    # s23 (rank1+rank2) and s10 (rank2+rank1) tie for the top; s27 trails.
    assert set(ids[:2]) == {"s23", "s10"}
    assert ids[-1] == "s27"
    scores = {s.chunk.id: s.score for s in fused.unwrap()}
    assert scores["s23"] == pytest.approx(scores["s10"])
    assert scores["s23"] > scores["s27"]


async def test_hybrid_tolerates_one_failing_retriever() -> None:
    ok = _StaticRetriever("dense", Ok(_scored(["s23"])))
    failed = _StaticRetriever("bm25", Err(RetrievalError("bm25_retrieval_failed")))
    result = await HybridRetriever([ok, failed]).retrieve("q", k=5)
    assert result.is_ok()
    assert [s.chunk.id for s in result.unwrap()] == ["s23"]


async def test_hybrid_errors_only_when_all_fail() -> None:
    a = _StaticRetriever("dense", Err(RetrievalError("dense_retrieval_failed")))
    b = _StaticRetriever("bm25", Err(RetrievalError("bm25_retrieval_failed")))
    result = await HybridRetriever([a, b]).retrieve("q")
    assert result.is_err()
    assert result.unwrap_err().context["retrievers"] == 2
