"""Local, free sentence-embedding adapter.

Implements the domain :class:`~clauseiq.domain.ports.Embedder` port using
``sentence-transformers`` (default model ``all-MiniLM-L6-v2``: 384-dim, runs
locally, no API cost). The model is loaded lazily on first use and reused.

``sentence-transformers`` is synchronous and CPU/GPU-bound, so every encode call
is dispatched to a worker thread via :func:`asyncio.to_thread` to keep the event
loop responsive (async-first). Embeddings are L2-normalised so a dot product
equals cosine similarity, matching the cosine space used in ChromaDB.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from clauseiq.config import settings
from clauseiq.domain.exceptions import EmbeddingError
from clauseiq.logging_config import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = get_logger(__name__)


class SentenceTransformerEmbedder:
    """Embeds text locally with a sentence-transformers model.

    Args:
        model_name: Hugging Face / sentence-transformers model id. Defaults to
            the configured embedding model.
        device: Optional torch device override (e.g. ``"cpu"``, ``"cuda"``,
            ``"mps"``). ``None`` lets the library auto-select.
    """

    def __init__(self, model_name: str | None = None, *, device: str | None = None) -> None:
        self._model_name = model_name or settings.embedding_model
        self._device = device
        self._model: SentenceTransformer | None = None

    def _ensure_model(self) -> SentenceTransformer:
        """Load (once) and return the underlying model, wrapping load failures."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name, device=self._device)
            except Exception as exc:  # external boundary: surface as a domain error
                raise EmbeddingError(
                    "model_load_failed", cause=exc, model=self._model_name
                ) from exc
            log.info("embedder_loaded", model=self._model_name, dimension=self.dimension)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encode (runs in a worker thread)."""
        model = self._ensure_model()
        try:
            raw = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        except Exception as exc:  # external boundary: surface as a domain error
            raise EmbeddingError("encode_failed", cause=exc, count=len(texts)) from exc
        # Concrete conversion (no Any leakage) to list[list[float]].
        return [[float(value) for value in vector] for vector in raw]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents for indexing."""
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, list(texts))

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval."""
        vectors = await asyncio.to_thread(self._encode, [text])
        return vectors[0]

    @property
    def dimension(self) -> int:
        """Embedding dimensionality of the loaded model."""
        dim = self._ensure_model().get_sentence_embedding_dimension()
        return int(dim) if dim is not None else 0


__all__ = ["SentenceTransformerEmbedder"]
