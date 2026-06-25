"""Unit tests for SentenceTransformerEmbedder (real model is not loaded).

The lazily-loaded model is replaced with a lightweight fake so these stay fast,
offline unit tests; the async dispatch, conversion, and error wrapping are what
we verify here.
"""

from __future__ import annotations

import pytest

from clauseiq.domain.exceptions import EmbeddingError
from clauseiq.infrastructure.vectorstore.embedder import SentenceTransformerEmbedder


class _FakeModel:
    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> list[list[float]]:
        return [[float(len(text)), 0.0] for text in texts]

    def get_sentence_embedding_dimension(self) -> int:
        return 2


class _ExplodingModel:
    def encode(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
        raise RuntimeError("cuda exploded")

    def get_sentence_embedding_dimension(self) -> int:
        return 2


def _embedder_with(model: object) -> SentenceTransformerEmbedder:
    embedder = SentenceTransformerEmbedder("fake-model")
    # Inject the fake to bypass the real (network/download) model load.
    embedder._model = model  # type: ignore[assignment]
    return embedder


async def test_embed_documents_returns_vectors() -> None:
    embedder = _embedder_with(_FakeModel())
    vectors = await embedder.embed_documents(["ab", "abc"])
    assert vectors == [[2.0, 0.0], [3.0, 0.0]]


async def test_embed_documents_empty_short_circuits() -> None:
    assert await _embedder_with(_FakeModel()).embed_documents([]) == []


async def test_embed_query_returns_single_vector() -> None:
    assert await _embedder_with(_FakeModel()).embed_query(" abcd") == [5.0, 0.0]


def test_dimension_reads_from_model() -> None:
    assert _embedder_with(_FakeModel()).dimension == 2


async def test_encode_failure_is_wrapped() -> None:
    embedder = _embedder_with(_ExplodingModel())
    with pytest.raises(EmbeddingError) as exc_info:
        await embedder.embed_query("boom")
    assert exc_info.value.code == "EmbeddingError"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
