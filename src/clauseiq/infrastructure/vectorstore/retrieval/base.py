"""Common base for retrieval strategies (the Strategy pattern's interface).

Concrete strategies (``DenseRetriever``, ``BM25Retriever``, ``HybridRetriever``)
subclass :class:`BaseRetriever` and structurally satisfy the domain
:class:`~clauseiq.domain.ports.Retriever` port.

Error/empty semantics (consistent across all strategies):

* **Infrastructure failure** (embedder/store/index error) -> ``Err(RetrievalError)``.
* **Ran fine, found nothing** -> ``Ok([])``. Returning empty (rather than an
  error) lets the hybrid fuser combine sources cleanly when only some return
  hits; the *caller* (repository/use case) decides whether zero total results is
  a low-confidence condition.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from clauseiq.domain.entities import ScoredChunk
from clauseiq.domain.exceptions import RetrievalError
from clauseiq.domain.result import Result


class BaseRetriever(ABC):
    """Abstract retrieval strategy returning ranked :class:`ScoredChunk` results."""

    name: ClassVar[str] = "base"

    @abstractmethod
    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        """Return up to ``k`` chunks relevant to ``query`` (or an error)."""
        raise NotImplementedError


__all__ = ["BaseRetriever"]
