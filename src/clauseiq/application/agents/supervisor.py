"""Supervisor agent (Gemini Flash) — triage, segmentation, retrieval planning.

The first node. It uses the fast orchestration model to:

1. decide whether the input is actually a contract (a cheap input guardrail),
2. segment it into clauses with a best-guess type, and
3. propose legal-topic queries for the retriever.

Output is a validated :class:`SegmentationResult` — no free-text parsing — so
downstream nodes receive structured data.
"""

from __future__ import annotations

from typing import ClassVar

from clauseiq.application.agents.state import AnalysisState
from clauseiq.application.schemas import SegmentationResult
from clauseiq.domain.value_objects import ClauseType
from clauseiq.infrastructure.llm.base import LLMClient
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

_CLAUSE_TYPES = ", ".join(member.value for member in ClauseType)

_SYSTEM = (
    "You are a contract-triage assistant for Indian law. You segment contracts "
    "into individual clauses and plan legal research. Be precise and never invent "
    "clause text — copy it verbatim from the input."
)

_PROMPT_TEMPLATE = (
    "Analyse the following document.\n"
    "1. Set is_contract=false if it is not a contract/agreement.\n"
    "2. If it is a contract, split it into individual clauses. For each clause give "
    "its 0-based index, an optional heading, the verbatim text, and the best-fitting "
    "clause_type from this set: {clause_types}. Use 'other' if none fit.\n"
    "3. Propose 3-8 short retrieval_queries (legal topics) to find the Indian law "
    "relevant to the riskier clauses.\n\n"
    "DOCUMENT:\n{contract_text}"
)


class SupervisorAgent:
    """LangGraph node: segments the contract and plans retrieval (Flash)."""

    name: ClassVar[str] = "supervisor"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def __call__(self, state: AnalysisState) -> dict[str, object]:
        contract_text = state["contract_text"]
        prompt = _PROMPT_TEMPLATE.format(clause_types=_CLAUSE_TYPES, contract_text=contract_text)
        result = await self._llm.generate_structured(
            prompt, SegmentationResult, system=_SYSTEM, temperature=0.1
        )
        if result.is_err():
            error = result.unwrap_err()
            log.error("supervisor_failed", code=error.message)
            return {
                "is_contract": False,
                "clauses": [],
                "retrieval_queries": [],
                "error": f"segmentation_failed:{error.message}",
            }

        segmentation = result.unwrap()
        if not segmentation.is_contract or not segmentation.clauses:
            log.info("supervisor_not_a_contract")
            return {
                "is_contract": False,
                "clauses": list(segmentation.clauses),
                "retrieval_queries": [],
                "error": None,
            }

        log.info(
            "supervisor_complete",
            clauses=len(segmentation.clauses),
            queries=len(segmentation.retrieval_queries),
        )
        return {
            "is_contract": True,
            "clauses": list(segmentation.clauses),
            "retrieval_queries": list(segmentation.retrieval_queries),
            "error": None,
        }


__all__ = ["SupervisorAgent"]
