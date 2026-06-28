"""Tests for the MCP tools and server (fakes injected; no model/LLM)."""

from __future__ import annotations

from datetime import date

import pytest

import clauseiq.interfaces.mcp.tools as mcp_tools
from clauseiq.application.schemas import ContractAnalysis
from clauseiq.domain.entities import Chunk, Citation, ScoredChunk
from clauseiq.domain.exceptions import LawSectionNotFoundError, RepositoryError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.domain.value_objects import Jurisdiction, LawCode
from clauseiq.infrastructure.repositories.law import ChromaLawRepository

_SECTION_27 = Citation(
    law_code=LawCode.ICA_1872,
    section_number="27",
    section_title="Agreement in restraint of trade, void",
    snippet="Every agreement by which anyone is restrained ... is void.",
    effective_date=date(1872, 9, 1),
)

_HITS = [
    ScoredChunk(
        chunk=Chunk(
            id="ICA_1872:s27::c0",
            text="restraint of trade is void",
            metadata={
                "law_code": "ICA_1872",
                "section_number": "27",
                "section_title": "Restraint of trade",
                "section_text": "Every agreement ... is void.",
            },
        ),
        score=0.03,
    )
]


class _FakeRepo:
    async def search(
        self, query: str, k: int = 5, *, jurisdiction: object = None
    ) -> Result[list[ScoredChunk], RepositoryError]:
        return Ok(_HITS[:k])

    async def get_section(
        self, law_code: LawCode, section_number: str
    ) -> Result[Citation, RepositoryError]:
        if law_code is LawCode.ICA_1872 and section_number == "27":
            return Ok(_SECTION_27)
        return Err(LawSectionNotFoundError("not_found", section=section_number))

    def citation_from_scored(self, scored: ScoredChunk) -> Citation:
        return ChromaLawRepository.to_citation(scored.chunk, relevance_score=scored.score)

    async def count(self) -> int:
        return 1


class _StubAnalyzer:
    async def analyze(self, request: object) -> Result[ContractAnalysis, object]:
        analysis = ContractAnalysis.build(
            contract_id="c1",
            jurisdiction=Jurisdiction.IN_MH,
            flags=[],
            corpus_version="ICA-1872-indiacode-2026-06-25",
            disclaimer="Not legal advice.",
        )
        return Ok(analysis)


@pytest.fixture(autouse=True)
def _reset_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_tools._context, "_repo", _FakeRepo())
    monkeypatch.setattr(mcp_tools._context, "_analyzer", _StubAnalyzer())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ICA_1872:27", (LawCode.ICA_1872, "27")),
        ("Section 27", (LawCode.ICA_1872, "27")),
        ("s. 23A", (LawCode.ICA_1872, "23A")),
    ],
)
def test_parse_citation(text: str, expected: tuple[LawCode, str]) -> None:
    assert mcp_tools._parse_citation(text) == expected


def test_parse_citation_without_number() -> None:
    assert mcp_tools._parse_citation("no section here") is None


async def test_search_indian_law_returns_sections() -> None:
    result = await mcp_tools.search_indian_law("restraint of trade", k=3)
    assert result["sections"][0]["section_number"] == "27"
    assert result["sections"][0]["amendment_note"] is not None


async def test_verify_citation_found() -> None:
    result = await mcp_tools.verify_citation("restraint of trade is void", "Section 27")
    assert result["verified"] is True
    assert result["matched_section"]["reference"] == "Section 27, Indian Contract Act, 1872"


async def test_verify_citation_not_found() -> None:
    result = await mcp_tools.verify_citation("made up", "Section 999")
    assert result["verified"] is False


async def test_analyze_contract_rejects_short_input() -> None:
    result = await mcp_tools.analyze_contract("too short")
    assert result["error"] == "invalid_input"


async def test_analyze_contract_returns_serialised_analysis() -> None:
    result = await mcp_tools.analyze_contract("x" * 200)
    assert result["flag_count"] == 0
    assert result["corpus_version"] == "ICA-1872-indiacode-2026-06-25"


async def test_server_registers_three_tools() -> None:
    from clauseiq.interfaces.mcp.server import mcp

    registered = await mcp.list_tools()
    names = {tool.name for tool in registered}
    assert names == {"analyze_contract", "search_indian_law", "verify_citation"}
