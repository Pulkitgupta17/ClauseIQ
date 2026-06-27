"""Citation Verifier agent — the anti-hallucination gate.

The last node. Every citation the analyzer proposed is checked against the law
corpus via ``LawRepository.get_section``: a citation survives only if that exact
section actually exists. Unverifiable citations are dropped (logged), so a
flag's legal backing is always real. The agent then assembles validated domain
:class:`RiskFlag` objects (mapping the 1-5 score to the ``Severity`` enum and
the clause type to ``ClauseType``).
"""

from __future__ import annotations

from typing import ClassVar

from clauseiq.application.agents.state import AnalysisState
from clauseiq.application.schemas import ProposedCitation, SegmentedClause, coerce_clause_type
from clauseiq.domain.entities import Citation, RiskFlag
from clauseiq.domain.exceptions import ValidationError
from clauseiq.domain.ports import LawRepository
from clauseiq.domain.value_objects import LawCode, Severity
from clauseiq.logging_config import get_logger

log = get_logger(__name__)


def _coerce_law_code(value: str) -> LawCode:
    try:
        return LawCode(value.strip())
    except ValueError:
        return LawCode.OTHER


class CitationVerifierAgent:
    """LangGraph node: verifies citations and builds domain risk flags."""

    name: ClassVar[str] = "citation_verifier"

    def __init__(self, law_repo: LawRepository) -> None:
        self._law_repo = law_repo

    async def _verify_citations(self, proposed: list[ProposedCitation]) -> list[Citation]:
        """Return only the proposed citations that exist in the corpus."""
        verified: list[Citation] = []
        for citation in proposed:
            law_code = _coerce_law_code(citation.law_code)
            result = await self._law_repo.get_section(law_code, citation.section_number)
            if result.is_ok():
                verified.append(result.unwrap())
            else:
                log.info(
                    "citation_rejected",
                    law_code=citation.law_code,
                    section=citation.section_number,
                )
        return verified

    async def __call__(self, state: AnalysisState) -> dict[str, object]:
        raw_flags = state.get("raw_flags", [])
        contract_id = state.get("contract_id", "contract")
        clause_by_index: dict[int, SegmentedClause] = {
            clause.index: clause for clause in state.get("clauses", [])
        }

        flags: list[RiskFlag] = []
        for raw in raw_flags:
            clause = clause_by_index.get(raw.clause_index)
            if clause is None:
                continue
            try:
                severity = Severity.from_score(raw.severity_score)
            except ValidationError:
                continue  # Pydantic should have caught this; guard defensively.
            verified = await self._verify_citations(raw.citations)
            flags.append(
                RiskFlag(
                    clause_id=f"{contract_id}:cl{clause.index}",
                    clause_type=coerce_clause_type(raw.clause_type),
                    severity=severity,
                    rationale=raw.rationale,
                    citations=tuple(verified),
                    confidence=raw.confidence,
                    suggested_action=raw.suggested_action,
                )
            )

        log.info("citation_verifier_complete", flags=len(flags))
        return {"flags": flags}


__all__ = ["CitationVerifierAgent"]
