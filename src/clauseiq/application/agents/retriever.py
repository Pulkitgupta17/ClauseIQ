"""Retriever agent — fetches relevant Indian law for the contract.

No LLM: it runs each of the supervisor's retrieval queries through the hybrid
``LawRepository`` and merges the hits into a single, de-duplicated, score-ranked
pool capped at ``pool_size``. The analyzer later draws per-clause context from
this pool. Falls back to clause text as queries if the supervisor produced none.
"""

from __future__ import annotations

from typing import ClassVar

from clauseiq.application.agents.state import AnalysisState
from clauseiq.domain.entities import ScoredChunk
from clauseiq.domain.ports import LawRepository
from clauseiq.logging_config import get_logger

log = get_logger(__name__)


class RetrieverAgent:
    """LangGraph node: builds the relevant-law pool via hybrid retrieval."""

    name: ClassVar[str] = "retriever"

    def __init__(
        self, law_repo: LawRepository, *, per_query_k: int = 5, pool_size: int = 12
    ) -> None:
        self._law_repo = law_repo
        self._per_query_k = per_query_k
        self._pool_size = pool_size

    async def __call__(self, state: AnalysisState) -> dict[str, object]:
        queries = list(state.get("retrieval_queries") or [])
        if not queries:
            queries = [clause.text for clause in state.get("clauses", [])]

        best_by_id: dict[str, ScoredChunk] = {}
        for query in queries:
            if not query.strip():
                continue
            result = await self._law_repo.search(query, self._per_query_k)
            if result.is_err():
                log.warning("retriever_query_failed", code=result.unwrap_err().message)
                continue
            for scored in result.unwrap():
                existing = best_by_id.get(scored.chunk.id)
                if existing is None or scored.score > existing.score:
                    best_by_id[scored.chunk.id] = scored

        pool = sorted(best_by_id.values(), key=lambda s: s.score, reverse=True)[: self._pool_size]
        log.info("retriever_complete", queries=len(queries), pool=len(pool))
        return {"law_pool": pool}


__all__ = ["RetrieverAgent"]
