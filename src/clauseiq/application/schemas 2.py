"""Pydantic I/O contracts for the application boundary.

Three groups of models:

* **API I/O** — request/response shapes for the HTTP and MCP interfaces
  (``ContractAnalysisRequest``, ``ContractAnalysis``, ``RiskFlagOut``,
  ``CitationOut``, ``LawSectionOut``, ``VerificationResult``).
* **LLM structured output** — the schemas the agents force the LLM to fill, so
  agent output is validated data, never parsed prose (``SegmentationResult``,
  ``RiskAnalysisResult`` and their parts).
* **Converters** from domain entities to API models.

The frontend's Zod schemas mirror the API I/O models here (single source of
truth on the backend).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from clauseiq.domain.entities import Citation, RiskFlag
from clauseiq.domain.value_objects import ClauseType, Jurisdiction, Severity


def coerce_clause_type(value: str) -> ClauseType:
    """Map an LLM-provided clause-type string to a :class:`ClauseType`.

    Falls back to ``ClauseType.OTHER`` for unrecognised values, so a creative
    LLM label never breaks the pipeline.
    """
    try:
        return ClauseType(value.strip().lower())
    except ValueError:
        return ClauseType.OTHER


# --- LLM structured output ---------------------------------------------------


class SegmentedClause(BaseModel):
    """One clause as segmented by the supervisor (Flash)."""

    index: int = Field(ge=0, description="0-based position of the clause in the contract.")
    heading: str | None = Field(default=None, description="Clause heading/number, if any.")
    text: str = Field(min_length=1, description="Verbatim clause text.")
    clause_type: str = Field(description="Best-guess clause category (see ClauseType values).")


class SegmentationResult(BaseModel):
    """Supervisor output: clauses + retrieval queries (no free-text parsing)."""

    is_contract: bool = Field(description="False if the input is not a contract.")
    clauses: list[SegmentedClause] = Field(default_factory=list)
    retrieval_queries: list[str] = Field(
        default_factory=list, description="Legal-topic queries to retrieve relevant law."
    )


class ProposedCitation(BaseModel):
    """A citation the analyzer proposes; verified later against the corpus."""

    law_code: str = Field(description="Statute code, e.g. ICA_1872.")
    section_number: str = Field(description="Section number, e.g. '23'.")


class AnalyzedFlag(BaseModel):
    """One risk flag as produced by the analyzer (Pro), severity on a 1-5 scale."""

    clause_index: int = Field(ge=0)
    clause_type: str
    severity_score: int = Field(ge=1, le=5, description="1=info ... 5=critical.")
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_action: str | None = None
    citations: list[ProposedCitation] = Field(default_factory=list)


class RiskAnalysisResult(BaseModel):
    """Analyzer output: all flags from one structured call."""

    flags: list[AnalyzedFlag] = Field(default_factory=list)


# --- API I/O -----------------------------------------------------------------


class ContractAnalysisRequest(BaseModel):
    """Request body for contract analysis."""

    contract_text: str = Field(min_length=100, description="Raw contract text.")
    jurisdiction: Jurisdiction = Jurisdiction.IN_MH


class CitationOut(BaseModel):
    """A verified citation to a section of Indian law."""

    law_code: str
    section_number: str
    section_title: str
    reference: str
    snippet: str
    source_url: str | None = None
    effective_date: date | None = None
    last_amended: date | None = None
    source_fetched_at: date | None = None
    relevance_score: float | None = None
    amendment_note: str | None = None

    @classmethod
    def from_domain(cls, citation: Citation, *, amendment_note: str | None = None) -> CitationOut:
        return cls(
            law_code=citation.law_code.value,
            section_number=citation.section_number,
            section_title=citation.section_title,
            reference=citation.reference,
            snippet=citation.snippet,
            source_url=citation.source_url,
            effective_date=citation.effective_date,
            last_amended=citation.last_amended,
            source_fetched_at=citation.source_fetched_at,
            relevance_score=citation.relevance_score,
            amendment_note=amendment_note,
        )


class RiskFlagOut(BaseModel):
    """A flagged clause with severity, rationale, and verified citations."""

    clause_id: str
    clause_heading: str | None = None
    clause_excerpt: str
    clause_type: str
    severity_score: int = Field(ge=1, le=5)
    severity_label: str
    rationale: str
    confidence: float
    suggested_action: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls,
        flag: RiskFlag,
        *,
        clause_excerpt: str,
        clause_heading: str | None,
        citations: list[CitationOut],
    ) -> RiskFlagOut:
        return cls(
            clause_id=flag.clause_id,
            clause_heading=clause_heading,
            clause_excerpt=clause_excerpt,
            clause_type=flag.clause_type.value,
            severity_score=flag.severity.score,
            severity_label=flag.severity.label,
            rationale=flag.rationale,
            confidence=flag.confidence,
            suggested_action=flag.suggested_action,
            citations=citations,
        )


class ContractAnalysis(BaseModel):
    """The full analysis result returned to the caller."""

    contract_id: str
    jurisdiction: str
    flag_count: int
    highest_severity: str | None = None
    flags: list[RiskFlagOut] = Field(default_factory=list)
    corpus_version: str
    disclaimer: str

    @classmethod
    def build(
        cls,
        *,
        contract_id: str,
        jurisdiction: Jurisdiction,
        flags: list[RiskFlagOut],
        corpus_version: str,
        disclaimer: str,
    ) -> ContractAnalysis:
        highest = (
            max((Severity.from_score(f.severity_score) for f in flags), default=None)
            if flags
            else None
        )
        return cls(
            contract_id=contract_id,
            jurisdiction=jurisdiction.value,
            flag_count=len(flags),
            highest_severity=highest.label if highest is not None else None,
            flags=flags,
            corpus_version=corpus_version,
            disclaimer=disclaimer,
        )


class LawSectionOut(BaseModel):
    """A statutory section returned from a law search or drill-down."""

    law_code: str
    section_number: str
    section_title: str
    reference: str
    snippet: str
    relevance_score: float | None = None
    source_url: str | None = None
    effective_date: date | None = None
    last_amended: date | None = None
    amendment_note: str | None = None

    @classmethod
    def from_citation(
        cls, citation: Citation, *, amendment_note: str | None = None
    ) -> LawSectionOut:
        return cls(
            law_code=citation.law_code.value,
            section_number=citation.section_number,
            section_title=citation.section_title,
            reference=citation.reference,
            snippet=citation.snippet,
            relevance_score=citation.relevance_score,
            source_url=citation.source_url,
            effective_date=citation.effective_date,
            last_amended=citation.last_amended,
            amendment_note=amendment_note,
        )


class VerificationResult(BaseModel):
    """Result of verifying a claimed citation against the corpus."""

    verified: bool
    citation: str
    reason: str
    matched_section: LawSectionOut | None = None


__all__ = [
    "AnalyzedFlag",
    "CitationOut",
    "ContractAnalysis",
    "ContractAnalysisRequest",
    "LawSectionOut",
    "ProposedCitation",
    "RiskAnalysisResult",
    "RiskFlagOut",
    "SegmentationResult",
    "SegmentedClause",
    "VerificationResult",
    "coerce_clause_type",
]
