"""Integration tests for the ChromaDB adapter against an in-memory client.

Uses ``chromadb.EphemeralClient`` (no network, no persistence). Embeddings are
supplied explicitly, so Chroma's default embedding function is never invoked.
"""

from __future__ import annotations

import chromadb
import pytest

from clauseiq.domain.entities import Chunk
from clauseiq.domain.exceptions import VectorStoreError
from clauseiq.infrastructure.vectorstore.chroma import ChromaVectorStore

pytestmark = pytest.mark.integration


def _store() -> ChromaVectorStore:
    return ChromaVectorStore(chromadb.EphemeralClient(), collection_name="test_law")


async def test_add_count_query_get_all_roundtrip() -> None:
    store = _store()
    chunks = [
        Chunk(
            id="s23",
            text="unlawful object makes an agreement void",
            metadata={"law_code": "ICA_1872"},
        ),
        Chunk(
            id="s10", text="free consent of competent parties", metadata={"law_code": "ICA_1872"}
        ),
    ]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]

    await store.add(chunks, embeddings)
    assert await store.count() == 2

    nearest = await store.query([0.95, 0.05], k=1)
    assert len(nearest) == 1
    assert nearest[0].chunk.id == "s23"
    assert nearest[0].score == pytest.approx(1.0, abs=0.1)

    all_chunks = await store.get_all()
    assert {chunk.id for chunk in all_chunks} == {"s23", "s10"}


async def test_metadata_filter_scopes_query() -> None:
    store = _store()
    await store.add(
        [
            Chunk(id="a", text="alpha", metadata={"law_code": "ICA_1872"}),
            Chunk(id="b", text="beta", metadata={"law_code": "CPA_2019"}),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )
    scoped = await store.query([1.0, 0.0], k=5, where={"law_code": "CPA_2019"})
    assert [chunk.chunk.id for chunk in scoped] == ["b"]


async def test_add_rejects_count_mismatch() -> None:
    store = _store()
    with pytest.raises(VectorStoreError):
        await store.add([Chunk(id="a", text="alpha")], [[1.0, 0.0], [0.0, 1.0]])
