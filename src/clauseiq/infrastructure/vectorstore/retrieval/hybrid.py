"""Hybrid retrieval via Reciprocal Rank Fusion (RRF).

Combines dense (semantic) and BM25 (lexical) results so the system catches both
paraphrased meaning *and* exact legal terms. We fuse with **RRF** rather than
mixing raw scores because BM25 scores and cosine similarities live on different,
incomparable scales — RRF uses only each result's *rank* in each list, so no
normalisation or score calibration is required.

RRF score for a document ``d``:

    score(d) = Σ_retrievers  1 / (rrf_k + rank_r(d))

where ``rank_r(d)`` is ``d``'s 1-based position in retriever ``r``'s list.
``rrf_k`` (default 60, the value from the original Cormack et al. RRF paper)
damps the influence of very high ranks; larger values flatten the contribution
of top positions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import ClassVar

from clauseiq.domain.entities import Chunk, ScoredChunk
from clauseiq.domain.exceptions import RetrievalError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.infrastructure.vectorstore.retrieval.base import BaseRetriever

# Canonical RRF constant from the original paper; tunable per retriever instance.
_DEFAULT_RRF_K = 60
# How many candidates to pull from each retriever before fusing.
_DEFAULT_FETCH_K = 20


class HybridRetriever(BaseRetriever):
    """Fuses several retrievers' rankings with Reciprocal Rank Fusion.

    Args:
        retrievers: The strategies to fuse (typically dense + BM25).
        rrf_k: RRF damping constant (default 60).
        fetch_k: Candidates to request from each retriever before fusion.

    Raises:
        ValueError: If no retrievers are supplied.
    """

    name: ClassVar[str] = "hybrid"

    def __init__(
        self,
        retrievers: Sequence[BaseRetriever],
        *,
        rrf_k: int = _DEFAULT_RRF_K,
        fetch_k: int = _DEFAULT_FETCH_K,
    ) -> None:
        if not retrievers:
            raise ValueError("HybridRetriever requires at least one retriever")
        self._retrievers = list(retrievers)
        self._rrf_k = rrf_k
        self._fetch_k = fetch_k

    async def retrieve(self, query: str, k: int = 5) -> Result[list[ScoredChunk], RetrievalError]:
        results = await asyncio.gather(
            *(retriever.retrieve(query, self._fetch_k) for retriever in self._retrievers)
        )
        ranked_lists = [result.unwrap() for result in results if result.is_ok()]
        if not ranked_lists:
            # Every underlying retriever failed -> propagate as a single error.
            return Err(RetrievalError("all_retrievers_failed", retrievers=len(self._retrievers)))
        fused = self._reciprocal_rank_fusion(ranked_lists)
        return Ok(fused[:k])

    def _reciprocal_rank_fusion(
        self, ranked_lists: Sequence[Sequence[ScoredChunk]]
    ) -> list[ScoredChunk]:
        """Fuse multiple ranked lists into one, ordered by descending RRF score."""
        fused_scores: dict[str, float] = {}
        chunks_by_id: dict[str, Chunk] = {}
        for ranked in ranked_lists:
            for rank, scored in enumerate(ranked, start=1):
                chunk_id = scored.chunk.id
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (
                    self._rrf_k + rank
                )
                chunks_by_id.setdefault(chunk_id, scored.chunk)
        fused = [
            ScoredChunk(chunk=chunks_by_id[chunk_id], score=score)
            for chunk_id, score in fused_scores.items()
        ]
        fused.sort(key=lambda scored: scored.score, reverse=True)
        return fused


__all__ = ["HybridRetriever"]
