"""Risk Analyzer agent (Gemini Pro) — scores clauses for unfairness.

The reasoning-heavy node. For each clause it builds context **deterministically**
(the clause text plus the law-pool chunks most lexically relevant to that clause)
and presents the assembled clause+law set to Gemini Pro in **one** structured
call. It deliberately does **not** pass the raw contract to the model — only the
already-segmented clauses — to avoid re-segmentation drift and prompt
contamination.

Output is a validated ``RiskAnalysisResult`` (severity on a strict 1-5 scale);
on a schema-validation failure (e.g. an out-of-range score) the call is retried.
"""

from __future__ import annotations

import re
from typing import ClassVar

from clauseiq.application.agents.state import AnalysisState
from clauseiq.application.schemas import RiskAnalysisResult, SegmentedClause
from clauseiq.domain.entities import ScoredChunk
from clauseiq.infrastructure.llm.base import LLMClient
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_SYSTEM = (
    "You are an expert Indian contract lawyer protecting the weaker party "
    "(a tenant, employee, freelancer, or small business). For each clause, decide "
    "if it is unfair or legally risky to that party and assign a severity from 1 to 5:\n"
    "  1 = info (standard/benign)\n"
    "  2 = low (minor, usually acceptable)\n"
    "  3 = medium (notable; negotiate)\n"
    "  4 = high (seriously one-sided or likely unenforceable)\n"
    "  5 = critical (egregious / void or illegal under Indian law)\n"
    "Only flag clauses that are genuinely risky. Cite ONLY sections present in the "
    "provided law context, using their law_code and section_number. If no provided "
    "section applies, return an empty citations list rather than inventing one."
)

_INSTRUCTION = (
    "Return a flag for each RISKY clause (skip benign ones). Each flag needs: "
    "clause_index, clause_type, severity_score (1-5), a concise rationale, "
    "confidence (0-1), an optional suggested_action, and citations drawn only from "
    "the law shown under that clause.\n\n"
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class RiskAnalyzerAgent:
    """LangGraph node: analyzes clauses against retrieved law (Pro)."""

    name: ClassVar[str] = "risk_analyzer"

    def __init__(
        self, llm: LLMClient, *, per_clause_law: int = 4, max_parse_retries: int = 2
    ) -> None:
        self._llm = llm
        self._per_clause_law = per_clause_law
        self._max_parse_retries = max_parse_retries

    def _select_context(
        self, clause: SegmentedClause, pool: list[ScoredChunk]
    ) -> list[ScoredChunk]:
        """Deterministically pick the law chunks most relevant to a clause."""
        clause_tokens = _tokens(clause.text)
        ranked = sorted(
            pool,
            key=lambda scored: len(clause_tokens & _tokens(scored.chunk.text)),
            reverse=True,
        )
        return list(ranked[: self._per_clause_law])

    def _build_prompt(self, clauses: list[SegmentedClause], pool: list[ScoredChunk]) -> str:
        blocks: list[str] = [_INSTRUCTION]
        for clause in clauses:
            blocks.append(
                f"CLAUSE {clause.index} [{clause.heading or clause.clause_type}]:\n{clause.text}"
            )
            context = self._select_context(clause, pool)
            if context:
                law_lines = "\n".join(
                    f"- [{scored.chunk.metadata.get('law_code', '?')} "
                    f"s{scored.chunk.metadata.get('section_number', '?')}] "
                    f"{scored.chunk.metadata.get('section_title', '')}: {scored.chunk.text[:400]}"
                    for scored in context
                )
                blocks.append(f"Relevant Indian law for clause {clause.index}:\n{law_lines}")
            else:
                blocks.append(f"Relevant Indian law for clause {clause.index}: (none retrieved)")
        return "\n\n".join(blocks)

    async def __call__(self, state: AnalysisState) -> dict[str, object]:
        clauses = state.get("clauses", [])
        pool = state.get("law_pool", [])
        if not clauses:
            return {"raw_flags": []}

        prompt = self._build_prompt(clauses, pool)
        for attempt in range(self._max_parse_retries + 1):
            result = await self._llm.generate_structured(
                prompt, RiskAnalysisResult, system=_SYSTEM, temperature=0.2
            )
            if result.is_ok():
                flags = result.unwrap().flags
                log.info("risk_analyzer_complete", flags=len(flags))
                return {"raw_flags": list(flags)}

            error = result.unwrap_err()
            if error.message == "structured_parse_failed" and attempt < self._max_parse_retries:
                log.warning("risk_analyzer_parse_retry", attempt=attempt)
                continue
            log.error("risk_analyzer_failed", code=error.message)
            return {"raw_flags": [], "error": f"analysis_failed:{error.message}"}
        return {"raw_flags": []}


__all__ = ["RiskAnalyzerAgent"]
