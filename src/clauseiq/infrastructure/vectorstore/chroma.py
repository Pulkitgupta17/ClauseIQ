"""ChromaDB adapter — storage only.

Implements the domain :class:`~clauseiq.domain.ports.VectorStore` port. By
design this adapter does **not** compute embeddings: vectors are produced by the
:class:`~clauseiq.infrastructure.vectorstore.embedder.SentenceTransformerEmbedder`
and passed in, keeping storage and embedding as separate, swappable concerns
(Single Responsibility).

The collection uses cosine space; Chroma returns cosine *distances*, which we
convert to a similarity *score* (``1 - distance``) so higher always means more
relevant, consistent with the other retrievers.

ChromaDB's client is synchronous, so collection operations run in a worker
thread via :func:`asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from clauseiq.config import settings
from clauseiq.domain.entities import Chunk, ScoredChunk
from clauseiq.domain.exceptions import VectorStoreError
from clauseiq.logging_config import get_logger

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection
    from chromadb.api.types import Embeddings, IncludeEnum

log = get_logger(__name__)

# Cosine space so distances are comparable across documents of different length.
_COLLECTION_METADATA = {"hnsw:space": "cosine"}


def _to_str_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    """Coerce Chroma's scalar metadata values to the domain's str-only mapping."""
    return {key: str(value) for key, value in metadata.items()}


class ChromaVectorStore:
    """A ChromaDB-backed vector store for a single collection.

    The Chroma client is injected (Dependency Injection) so tests can pass an
    in-memory ``EphemeralClient`` and production can pass a persistent or HTTP
    client. Use :func:`build_law_vector_store` for the settings-wired instance.
    """

    def __init__(self, client: ClientAPI, *, collection_name: str) -> None:
        self._client = client
        self._collection_name = collection_name
        self._collection: Collection | None = None

    def _ensure_collection(self) -> Collection:
        if self._collection is None:
            try:
                self._collection = self._client.get_or_create_collection(
                    name=self._collection_name,
                    metadata=_COLLECTION_METADATA,
                )
            except Exception as exc:  # external boundary
                raise VectorStoreError(
                    "collection_open_failed", cause=exc, collection=self._collection_name
                ) from exc
        return self._collection

    def _add_sync(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        collection = self._ensure_collection()
        collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=cast("Embeddings", [list(vector) for vector in embeddings]),
            documents=[chunk.text for chunk in chunks],
            metadatas=[dict(chunk.metadata) for chunk in chunks],
        )

    async def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        """Upsert chunks with their precomputed embeddings."""
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise VectorStoreError(
                "chunk_embedding_count_mismatch",
                chunks=len(chunks),
                embeddings=len(embeddings),
            )
        try:
            await asyncio.to_thread(self._add_sync, chunks, embeddings)
        except VectorStoreError:
            raise
        except Exception as exc:  # external boundary
            raise VectorStoreError("add_failed", cause=exc, count=len(chunks)) from exc
        log.info("vectorstore_add", collection=self._collection_name, count=len(chunks))

    def _query_sync(
        self,
        embedding: Sequence[float],
        k: int,
        where: Mapping[str, str] | None,
    ) -> list[ScoredChunk]:
        collection = self._ensure_collection()
        result = collection.query(
            query_embeddings=cast("Embeddings", [list(embedding)]),
            n_results=k,
            where=dict(where) if where else None,
            include=cast("list[IncludeEnum]", ["documents", "metadatas", "distances"]),
        )
        return self._parse_query_result(result)

    @staticmethod
    def _parse_query_result(result: Mapping[str, Any]) -> list[ScoredChunk]:
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        scored: list[ScoredChunk] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            chunk = Chunk(
                id=str(chunk_id),
                text=str(document),
                metadata=_to_str_metadata(metadata or {}),
            )
            scored.append(ScoredChunk(chunk=chunk, score=1.0 - float(distance)))
        return scored

    async def query(
        self,
        embedding: Sequence[float],
        k: int,
        *,
        where: Mapping[str, str] | None = None,
    ) -> list[ScoredChunk]:
        """Return the ``k`` nearest chunks, optionally filtered by metadata."""
        try:
            return await asyncio.to_thread(self._query_sync, embedding, k, where)
        except Exception as exc:  # external boundary
            raise VectorStoreError("query_failed", cause=exc) from exc

    def _get_all_sync(self, where: Mapping[str, str] | None) -> list[Chunk]:
        collection = self._ensure_collection()
        result = collection.get(
            where=dict(where) if where else None,
            include=cast("list[IncludeEnum]", ["documents", "metadatas"]),
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        return [
            Chunk(id=str(chunk_id), text=str(document), metadata=_to_str_metadata(metadata or {}))
            for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=False)
        ]

    async def get_all(self, *, where: Mapping[str, str] | None = None) -> list[Chunk]:
        """Return all stored chunks (used to build the BM25 sparse index)."""
        try:
            return await asyncio.to_thread(self._get_all_sync, where)
        except Exception as exc:  # external boundary
            raise VectorStoreError("get_all_failed", cause=exc) from exc

    async def count(self) -> int:
        """Return the number of chunks currently stored."""
        try:
            collection = await asyncio.to_thread(self._ensure_collection)
            return int(await asyncio.to_thread(collection.count))
        except Exception as exc:  # external boundary
            raise VectorStoreError("count_failed", cause=exc) from exc


def build_chroma_client() -> ClientAPI:
    """Build a Chroma client from settings.

    ``chroma_mode == "http"`` connects to a ChromaDB server (Docker compose);
    otherwise a local persistent client at ``chroma_persist_dir`` is used so the
    data pipeline runs with no external service (dev/CI/tests).
    """
    import chromadb

    if settings.chroma_mode == "http":
        http_client: ClientAPI = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port
        )
        return http_client
    persist_dir = settings.chroma_persist_dir
    persist_dir.mkdir(parents=True, exist_ok=True)
    persistent_client: ClientAPI = chromadb.PersistentClient(path=str(persist_dir))
    return persistent_client


def build_law_vector_store(client: ClientAPI | None = None) -> ChromaVectorStore:
    """Construct the law-corpus vector store wired from settings."""
    return ChromaVectorStore(
        client or build_chroma_client(),
        collection_name=settings.chroma_collection_law,
    )


__all__ = [
    "ChromaVectorStore",
    "build_chroma_client",
    "build_law_vector_store",
]
