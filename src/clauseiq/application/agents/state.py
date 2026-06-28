"""LangGraph shared state for the analysis pipeline.

Each agent node reads the keys it needs and returns a partial update; LangGraph
merges updates into this :class:`AnalysisState`. Keys are filled in pipeline
order (supervisor → retriever → analyzer → verifier), so ``total=False`` allows
partial population as the graph runs.
"""

from __future__ import annotations

from typing import TypedDict

from clauseiq.application.schemas import AnalyzedFlag, SegmentedClause
from clauseiq.domain.entities import RiskFlag, ScoredChunk

# Event names emitted as each node completes (consumed by the SSE stream).
NODE_EVENTS: dict[str, str] = {
    "supervisor": "supervisor_complete",
    "retriever": "retriever_complete",
    "risk_analyzer": "risk_analyzer_complete",
    "citation_verifier": "citation_verifier_complete",
}


class AnalysisState(TypedDict, total=False):
    """Mutable state threaded through the LangGraph pipeline."""

    # --- inputs ---
    contract_text: str
    jurisdiction: str
    contract_id: str

    # --- supervisor (Flash) outputs ---
    is_contract: bool
    clauses: list[SegmentedClause]
    retrieval_queries: list[str]

    # --- retriever outputs ---
    law_pool: list[ScoredChunk]

    # --- risk analyzer (Pro) outputs ---
    raw_flags: list[AnalyzedFlag]

    # --- citation verifier outputs (domain, verified) ---
    flags: list[RiskFlag]

    # --- control ---
    error: str | None


__all__ = ["NODE_EVENTS", "AnalysisState"]
