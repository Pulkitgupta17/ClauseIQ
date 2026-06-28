"""``analyze_contract`` use case — assembles and runs the agent pipeline.

Builds a LangGraph ``StateGraph`` (supervisor → retriever → risk_analyzer →
citation_verifier) and exposes two entry points on :class:`ContractAnalyzer`:

* :meth:`analyze` — run to completion, return a :class:`ContractAnalysis`.
* :meth:`stream` — yield a :class:`StreamEvent` as each agent completes, for the
  SSE endpoint. Event order: ``supervisor_start`` → ``supervisor_complete`` →
  ``retriever_complete`` → ``risk_analyzer_complete`` → ``citation_verifier_complete``
  → ``done`` (or ``error``).

Dependencies (LLM clients, law repository) are injected via :class:`AnalysisDeps`,
keeping this layer free of concrete adapters.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from clauseiq.application.agents.citation_verifier import CitationVerifierAgent
from clauseiq.application.agents.retriever import RetrieverAgent
from clauseiq.application.agents.risk_analyzer import RiskAnalyzerAgent
from clauseiq.application.agents.state import NODE_EVENTS, AnalysisState
from clauseiq.application.agents.supervisor import SupervisorAgent
from clauseiq.application.schemas import (
    CitationOut,
    ContractAnalysis,
    ContractAnalysisRequest,
    RiskFlagOut,
)
from clauseiq.domain.entities import RiskFlag
from clauseiq.domain.exceptions import AnalysisError, ClauseIQError, GuardrailError
from clauseiq.domain.ports import LawRepository
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.infrastructure.guardrails.injection_detector import detect_injection
from clauseiq.infrastructure.guardrails.input_filter import screen_input
from clauseiq.infrastructure.guardrails.output_filter import ensure_disclaimer
from clauseiq.infrastructure.llm.base import LLMClient
from clauseiq.infrastructure.observability.usage import usage_scope
from clauseiq.logging_config import ensure_trace, get_logger

log = get_logger(__name__)

DEFAULT_DISCLAIMER = (
    "ClauseIQ provides automated decision-support, not legal advice. Citations are "
    "to the Indian Contract Act, 1872; amendment history is not tracked. Consult a "
    "qualified lawyer and verify current law before acting."
)


class StreamEvent(BaseModel):
    """A single Server-Sent Event in the analysis stream."""

    event: str
    # Heterogeneous progress/result payload (JSON-serialisable).
    data: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnalysisDeps:
    """Injected dependencies for the analysis pipeline."""

    supervisor_llm: LLMClient
    analyzer_llm: LLMClient
    law_repo: LawRepository
    corpus_version: str
    disclaimer: str = DEFAULT_DISCLAIMER


def _route_after_supervisor(state: AnalysisState) -> str:
    """Continue only if the input is a contract and segmentation succeeded."""
    if state.get("is_contract") and not state.get("error"):
        return "continue"
    return "end"


def build_analysis_graph(deps: AnalysisDeps) -> Any:  # compiled LangGraph (untyped SDK)
    """Assemble and compile the multi-agent ``StateGraph``."""
    graph: Any = StateGraph(AnalysisState)
    graph.add_node("supervisor", SupervisorAgent(deps.supervisor_llm))
    graph.add_node("retriever", RetrieverAgent(deps.law_repo))
    graph.add_node("risk_analyzer", RiskAnalyzerAgent(deps.analyzer_llm))
    graph.add_node("citation_verifier", CitationVerifierAgent(deps.law_repo))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor", _route_after_supervisor, {"continue": "retriever", "end": END}
    )
    graph.add_edge("retriever", "risk_analyzer")
    graph.add_edge("risk_analyzer", "citation_verifier")
    graph.add_edge("citation_verifier", END)
    return graph.compile()


def _contract_id(contract_text: str) -> str:
    digest = hashlib.sha256(contract_text.encode("utf-8")).hexdigest()
    return f"contract-{digest[:12]}"


def _clause_index(clause_id: str) -> int:
    try:
        return int(clause_id.rsplit(":cl", 1)[-1])
    except ValueError:
        return -1


class ContractAnalyzer:
    """The contract-analysis use case (sync result or SSE stream)."""

    def __init__(self, deps: AnalysisDeps) -> None:
        self._deps = deps
        self._graph = build_analysis_graph(deps)

    def _initial_state(self, request: ContractAnalysisRequest) -> AnalysisState:
        return {
            "contract_text": request.contract_text,
            "jurisdiction": request.jurisdiction.value,
            "contract_id": _contract_id(request.contract_text),
            "error": None,
        }

    def _screen(self, request: ContractAnalysisRequest) -> GuardrailError | None:
        """Run input guardrails; return a :class:`GuardrailError` if rejected."""
        injection = detect_injection(request.contract_text)
        if injection.detected:
            log.warning("guardrail_injection_detected", matches=list(injection.matches))
            return GuardrailError("prompt_injection_detected", matches=list(injection.matches))
        assessment = screen_input(request.contract_text)
        if not assessment.accepted:
            log.info("guardrail_input_rejected", reason=assessment.reason)
            return GuardrailError("not_a_contract", reason=assessment.reason)
        return None

    async def analyze(
        self, request: ContractAnalysisRequest
    ) -> Result[ContractAnalysis, ClauseIQError]:
        """Run guardrails + the full pipeline and return the analysis (or an error)."""
        rejection = self._screen(request)
        if rejection is not None:
            return Err(rejection)
        with ensure_trace() as trace_id, usage_scope() as usage:
            final: dict[str, Any] = await self._graph.ainvoke(self._initial_state(request))
            outcome: Result[ContractAnalysis, ClauseIQError] = (
                Err(AnalysisError(str(final["error"])))
                if final.get("error") and not final.get("flags")
                else Ok(ensure_disclaimer(self._build_analysis(request, final)))
            )
            log.info(
                "analysis_complete",
                trace_id=trace_id,
                flags=len(final.get("flags", [])),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                cost_usd=round(usage.cost_usd, 6),
            )
        return outcome

    async def stream(self, request: ContractAnalysisRequest) -> AsyncIterator[StreamEvent]:
        """Run the pipeline, yielding an event as each agent completes."""
        rejection = self._screen(request)
        if rejection is not None:
            yield StreamEvent(event="error", data={"error": rejection.message, **rejection.context})
            return

        with ensure_trace() as trace_id, usage_scope() as usage:
            initial = self._initial_state(request)
            yield StreamEvent(
                event="supervisor_start", data={"contract_id": initial["contract_id"]}
            )

            final: dict[str, Any] = dict(initial)
            async for update in self._graph.astream(initial, stream_mode="updates"):
                for node_name, node_update in update.items():
                    if isinstance(node_update, dict):
                        final.update(node_update)
                    event_name = NODE_EVENTS.get(node_name)
                    if event_name is not None:
                        yield StreamEvent(event=event_name, data=_node_summary(node_name, final))

            if final.get("error") and not final.get("flags"):
                yield StreamEvent(event="error", data={"message": str(final["error"])})
                return
            analysis = ensure_disclaimer(self._build_analysis(request, final))
            log.info(
                "analysis_complete",
                trace_id=trace_id,
                total_tokens=usage.total_tokens,
                cost_usd=round(usage.cost_usd, 6),
            )
            yield StreamEvent(
                event="done",
                data={
                    "analysis": analysis.model_dump(mode="json"),
                    "usage": {
                        "total_tokens": usage.total_tokens,
                        "cost_usd": round(usage.cost_usd, 6),
                    },
                },
            )

    def _build_analysis(
        self, request: ContractAnalysisRequest, final: dict[str, Any]
    ) -> ContractAnalysis:
        clauses = {clause.index: clause for clause in final.get("clauses", [])}
        flags: list[RiskFlag] = final.get("flags", [])
        flag_outs: list[RiskFlagOut] = []
        for flag in flags:
            clause = clauses.get(_clause_index(flag.clause_id))
            citations = [
                CitationOut.from_domain(citation, amendment_note=citation.amendment_note)
                for citation in flag.citations
            ]
            flag_outs.append(
                RiskFlagOut.from_domain(
                    flag,
                    clause_excerpt=clause.text if clause else "",
                    clause_heading=clause.heading if clause else None,
                    citations=citations,
                )
            )
        return ContractAnalysis.build(
            contract_id=str(final.get("contract_id", "contract")),
            jurisdiction=request.jurisdiction,
            flags=flag_outs,
            corpus_version=self._deps.corpus_version,
            disclaimer=self._deps.disclaimer,
        )


def _node_summary(node_name: str, final: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe progress payload for a completed node."""
    if node_name == "supervisor":
        return {
            "clauses": len(final.get("clauses", [])),
            "is_contract": bool(final.get("is_contract")),
        }
    if node_name == "retriever":
        return {"law_sections": len(final.get("law_pool", []))}
    if node_name == "risk_analyzer":
        return {"candidate_flags": len(final.get("raw_flags", []))}
    if node_name == "citation_verifier":
        return {"flags": len(final.get("flags", []))}
    return {}


__all__ = [
    "DEFAULT_DISCLAIMER",
    "AnalysisDeps",
    "ContractAnalyzer",
    "StreamEvent",
    "build_analysis_graph",
]
