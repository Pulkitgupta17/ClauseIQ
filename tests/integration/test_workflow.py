"""Integration test: the full analyze_contract pipeline over real LangGraph.

The LLM and law repository are faked (deterministic, no API key), but the
LangGraph ``StateGraph`` and all four agents run for real, exercising routing,
state merging, SSE event order, and citation verification.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from clauseiq.application.schemas import (
    AnalyzedFlag,
    ContractAnalysisRequest,
    ProposedCitation,
    RiskAnalysisResult,
    SegmentationResult,
    SegmentedClause,
)
from clauseiq.application.workflows import AnalysisDeps, ContractAnalyzer
from clauseiq.domain.entities import Chunk, Citation, ScoredChunk
from clauseiq.domain.exceptions import LawSectionNotFoundError, LLMError, RepositoryError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode

_SECTION_27 = Citation(
    law_code=LawCode.ICA_1872,
    section_number="27",
    section_title="Agreement in restraint of trade, void",
    snippet="Every agreement by which anyone is restrained from exercising a lawful profession is void.",
    effective_date=date(1872, 9, 1),
)

_LAW_HITS = [
    ScoredChunk(
        chunk=Chunk(
            id="ICA_1872:s27::c0",
            text="restraint of trade is void",
            metadata={
                "law_code": "ICA_1872",
                "section_number": "27",
                "section_title": "Restraint of trade",
            },
        ),
        score=0.03,
    )
]

_CONTRACT = (
    "RENTAL AGREEMENT. 5. Lock-in: The tenant is locked in for 11 months and forfeits "
    "the full deposit on early exit. 9. Non-compete: The tenant shall not run any "
    "competing business within 5 km for 3 years after vacating the premises."
)


class _FakeLLM:
    model_name = "fake-flash-pro"

    def __init__(self, *, segmentation: SegmentationResult, analysis: RiskAnalysisResult) -> None:
        self._segmentation = segmentation
        self._analysis = analysis

    async def generate(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Result[str, LLMError]:
        return Ok("ok")

    async def generate_structured(self, prompt, schema, *, system=None, temperature=None):  # type: ignore[no-untyped-def]
        if schema is SegmentationResult:
            return Ok(self._segmentation)
        if schema is RiskAnalysisResult:
            return Ok(self._analysis)
        return Err(LLMError("unexpected_schema"))


class _FakeLawRepo:
    def __init__(self, sections: Mapping[str, Citation], hits: Sequence[ScoredChunk]) -> None:
        self._sections = dict(sections)
        self._hits = list(hits)

    async def search(
        self, query: str, k: int = 5, *, jurisdiction: Jurisdiction | None = None
    ) -> Result[list[ScoredChunk], RepositoryError]:
        return Ok(self._hits[:k])

    async def get_section(
        self, law_code: LawCode, section_number: str
    ) -> Result[Citation, RepositoryError]:
        citation = self._sections.get(section_number) if law_code is LawCode.ICA_1872 else None
        if citation is not None:
            return Ok(citation)
        return Err(LawSectionNotFoundError("section_not_found", section=section_number))

    async def count(self) -> int:
        return len(self._sections)


def _deps() -> AnalysisDeps:
    segmentation = SegmentationResult(
        is_contract=True,
        clauses=[
            SegmentedClause(
                index=0,
                heading="9. Non-compete",
                text="shall not run any competing business within 5 km for 3 years",
                clause_type="non_compete",
            ),
        ],
        retrieval_queries=["restraint of trade", "non-compete enforceability"],
    )
    analysis = RiskAnalysisResult(
        flags=[
            AnalyzedFlag(
                clause_index=0,
                clause_type="non_compete",
                severity_score=4,
                rationale="A post-employment restraint of trade is void under s.27.",
                confidence=0.85,
                citations=[
                    ProposedCitation(law_code="ICA_1872", section_number="27"),
                    ProposedCitation(law_code="ICA_1872", section_number="999"),  # does not exist
                ],
            )
        ]
    )
    llm = _FakeLLM(segmentation=segmentation, analysis=analysis)
    return AnalysisDeps(
        supervisor_llm=llm,
        analyzer_llm=llm,
        law_repo=_FakeLawRepo({"27": _SECTION_27}, _LAW_HITS),
        corpus_version="ICA-1872-indiacode-2026-06-25",
    )


def _request() -> ContractAnalysisRequest:
    return ContractAnalysisRequest(contract_text=_CONTRACT, jurisdiction=Jurisdiction.IN_MH)


async def test_analyze_returns_flags_with_verified_citations() -> None:
    result = await ContractAnalyzer(_deps()).analyze(_request())
    assert result.is_ok()
    analysis = result.unwrap()
    assert analysis.flag_count == 1
    flag = analysis.flags[0]
    assert flag.clause_type == "non_compete"
    assert flag.severity_score == 4
    assert flag.severity_label == "high"
    # s27 verified and kept; s999 rejected by the citation verifier.
    assert [c.section_number for c in flag.citations] == ["27"]
    assert flag.citations[0].amendment_note is not None
    assert analysis.highest_severity == "high"
    assert analysis.corpus_version == "ICA-1872-indiacode-2026-06-25"


async def test_stream_emits_events_in_order() -> None:
    events = [event.event async for event in ContractAnalyzer(_deps()).stream(_request())]
    assert events == [
        "supervisor_start",
        "supervisor_complete",
        "retriever_complete",
        "risk_analyzer_complete",
        "citation_verifier_complete",
        "done",
    ]


async def test_stream_done_event_carries_serialisable_analysis() -> None:
    done_events = [
        e async for e in ContractAnalyzer(_deps()).stream(_request()) if e.event == "done"
    ]
    analysis = done_events[0].data["analysis"]
    assert analysis["flag_count"] == 1
    assert analysis["flags"][0]["citations"][0]["section_number"] == "27"


async def test_non_contract_short_circuits() -> None:
    deps = _deps()
    not_a_contract = AnalysisDeps(
        supervisor_llm=_FakeLLM(
            segmentation=SegmentationResult(is_contract=False, clauses=[], retrieval_queries=[]),
            analysis=RiskAnalysisResult(flags=[]),
        ),
        analyzer_llm=deps.analyzer_llm,
        law_repo=deps.law_repo,
        corpus_version=deps.corpus_version,
    )
    events = [e.event async for e in ContractAnalyzer(not_a_contract).stream(_request())]
    assert events == ["supervisor_start", "supervisor_complete", "done"]
    result = await ContractAnalyzer(not_a_contract).analyze(_request())
    assert result.is_ok()
    assert result.unwrap().flag_count == 0
