"""Integration tests for the HTTP API (analysis, SSE, law drill-down, health).

The analyzer and law repository are overridden with stubs via
``app.dependency_overrides``, so these tests never load a model or call an LLM —
they verify routing, serialization, SSE framing, and error mapping.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

from fastapi.testclient import TestClient

from clauseiq.application.schemas import ContractAnalysis, LawSectionOut, RiskFlagOut
from clauseiq.application.workflows import StreamEvent
from clauseiq.domain.entities import Citation
from clauseiq.domain.exceptions import AnalysisError, LawSectionNotFoundError, RepositoryError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode
from clauseiq.interfaces.api.dependencies import get_contract_analyzer, get_law_repository
from clauseiq.interfaces.api.main import create_app

_CONTRACT = (
    "RENTAL AGREEMENT made between landlord and tenant. The tenant shall not run any "
    "competing business within five kilometres for three years after vacating, and is "
    "locked in for eleven months forfeiting the entire security deposit on early exit."
)

_ANALYSIS = ContractAnalysis.build(
    contract_id="contract-abc",
    jurisdiction=Jurisdiction.IN_MH,
    flags=[
        RiskFlagOut(
            clause_id="contract-abc:cl0",
            clause_excerpt="shall not run any competing business",
            clause_type="non_compete",
            severity_score=4,
            severity_label="high",
            rationale="Restraint of trade is void under s.27.",
            confidence=0.85,
        )
    ],
    corpus_version="ICA-1872-indiacode-2026-06-25",
    disclaimer="Not legal advice.",
)

_EVENTS = [
    StreamEvent(event="supervisor_start", data={"contract_id": "contract-abc"}),
    StreamEvent(event="supervisor_complete", data={"clauses": 1}),
    StreamEvent(event="retriever_complete", data={"law_sections": 3}),
    StreamEvent(event="risk_analyzer_complete", data={"candidate_flags": 1}),
    StreamEvent(event="citation_verifier_complete", data={"flags": 1}),
    StreamEvent(event="done", data={"analysis": _ANALYSIS.model_dump(mode="json")}),
]


class _StubAnalyzer:
    def __init__(self, *, error: str | None = None) -> None:
        self._error = error

    async def analyze(self, request: object) -> Result[ContractAnalysis, AnalysisError]:
        if self._error is not None:
            return Err(AnalysisError(self._error))
        return Ok(_ANALYSIS)

    async def stream(self, request: object) -> AsyncIterator[StreamEvent]:
        for event in _EVENTS:
            yield event


class _StubLawRepo:
    async def search(
        self, query: str, k: int = 5, *, jurisdiction: object = None
    ) -> Result[list, RepositoryError]:
        return Ok([])

    async def get_section(
        self, law_code: LawCode, section_number: str
    ) -> Result[Citation, RepositoryError]:
        if law_code is LawCode.ICA_1872 and section_number == "27":
            return Ok(
                Citation(
                    law_code=LawCode.ICA_1872,
                    section_number="27",
                    section_title="Agreement in restraint of trade, void",
                    snippet="Every agreement ... is void.",
                    effective_date=date(1872, 9, 1),
                )
            )
        return Err(LawSectionNotFoundError("not_found", section=section_number))

    async def count(self) -> int:
        return 1


def _client(*, analyzer: _StubAnalyzer | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_contract_analyzer] = lambda: analyzer or _StubAnalyzer()
    app.dependency_overrides[get_law_repository] = _StubLawRepo
    return TestClient(app)


def test_analyze_returns_structured_result() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/analyze",
            json={"contract_text": _CONTRACT, "jurisdiction": "IN-MH"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["flag_count"] == 1
    assert body["flags"][0]["severity_label"] == "high"
    assert "X-Trace-Id" in response.headers


def test_analyze_validation_error_is_422() -> None:
    with _client() as client:
        response = client.post("/api/v1/analyze", json={"contract_text": "too short"})
    assert response.status_code == 422  # contract_text min_length not met


def test_analyze_llm_failure_maps_to_502() -> None:
    with _client(analyzer=_StubAnalyzer(error="analysis_failed:server_error")) as client:
        response = client.post(
            "/api/v1/analyze", json={"contract_text": _CONTRACT, "jurisdiction": "IN-MH"}
        )
    assert response.status_code == 502


def test_analyze_missing_key_maps_to_503() -> None:
    with _client(analyzer=_StubAnalyzer(error="segmentation_failed:api_key_missing")) as client:
        response = client.post(
            "/api/v1/analyze", json={"contract_text": _CONTRACT, "jurisdiction": "IN-MH"}
        )
    assert response.status_code == 503


def test_analyze_stream_emits_ordered_sse() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/analyze/stream",
            json={"contract_text": _CONTRACT, "jurisdiction": "IN-MH"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    order = [
        "event: supervisor_start",
        "event: supervisor_complete",
        "event: retriever_complete",
        "event: risk_analyzer_complete",
        "event: citation_verifier_complete",
        "event: done",
    ]
    positions = [body.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_law_drilldown_found_and_not_found() -> None:
    with _client() as client:
        ok = client.get("/api/v1/law/ICA_1872:27")
        missing = client.get("/api/v1/law/ICA_1872:999")
    assert ok.status_code == 200
    section = LawSectionOut.model_validate(ok.json())
    assert section.reference == "Section 27, Indian Contract Act, 1872"
    assert section.amendment_note is not None
    assert missing.status_code == 404


def test_healthz() -> None:
    with _client() as client:
        assert client.get("/healthz").json() == {"status": "ok"}
