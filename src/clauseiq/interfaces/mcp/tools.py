"""MCP tool implementations (the logic; registration lives in ``server.py``).

Heavy resources (law repository, analyzer) are built lazily and cached in a
module-level :data:`_context` so the three tools share one model load and BM25
index. Tools return plain JSON-serialisable dicts and never raise across the MCP
boundary — failures come back as ``{"error": ...}`` so Claude can react.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from clauseiq.application.schemas import (
    ContractAnalysisRequest,
    LawSectionOut,
    VerificationResult,
)
from clauseiq.application.workflows import AnalysisDeps, ContractAnalyzer
from clauseiq.config import settings
from clauseiq.domain.value_objects import LawCode
from clauseiq.infrastructure.llm.factory import LLMRole, get_llm_client
from clauseiq.infrastructure.repositories.law import ChromaLawRepository, build_law_repository
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

_SECTION_RE = re.compile(r"(\d+[A-Za-z]?)")


class ToolContext:
    """Lazily builds and caches the law repository and contract analyzer."""

    def __init__(self) -> None:
        self._repo: ChromaLawRepository | None = None
        self._analyzer: ContractAnalyzer | None = None
        self._lock = asyncio.Lock()

    async def law_repo(self) -> ChromaLawRepository:
        if self._repo is None:
            async with self._lock:
                if self._repo is None:
                    log.info("mcp_building_law_repository")
                    self._repo = await build_law_repository()
        return self._repo

    async def analyzer(self) -> ContractAnalyzer:
        if self._analyzer is None:
            repo = await self.law_repo()
            async with self._lock:
                if self._analyzer is None:
                    deps = AnalysisDeps(
                        supervisor_llm=get_llm_client(LLMRole.ORCHESTRATION),
                        analyzer_llm=get_llm_client(LLMRole.ANALYSIS),
                        law_repo=repo,
                        corpus_version=settings.corpus_version,
                    )
                    self._analyzer = ContractAnalyzer(deps)
        return self._analyzer


_context = ToolContext()


def _parse_citation(citation: str) -> tuple[LawCode, str] | None:
    """Parse a free-form citation into a law code + section number.

    When a ``LAW_CODE:section`` form is given, the section number is taken from
    after the colon so a year inside the law code (e.g. ``ICA_1872``) is not
    mistaken for the section.
    """
    _, separator, after_colon = citation.partition(":")
    search_in = after_colon if separator else citation
    match = _SECTION_RE.search(search_in)
    if match is None:
        return None
    law_code = LawCode.ICA_1872
    for code in LawCode:
        if code is LawCode.OTHER:
            continue
        if code.value in citation or code.value.replace("_", " ") in citation:
            law_code = code
            break
    return law_code, match.group(1)


async def analyze_contract(contract_text: str) -> dict[str, Any]:
    """Run the full multi-agent analysis on a contract; return the structured result."""
    try:
        request = ContractAnalysisRequest(contract_text=contract_text)
    except PydanticValidationError:
        return {
            "error": "invalid_input",
            "detail": "contract_text must be at least 100 characters.",
        }
    analyzer = await _context.analyzer()
    result = await analyzer.analyze(request)
    if result.is_err():
        return {"error": "analysis_failed", "reason": result.unwrap_err().message}
    return result.unwrap().model_dump(mode="json")


async def search_indian_law(query: str, k: int = 5) -> dict[str, Any]:
    """Hybrid-search the Indian Contract Act corpus; return the top sections."""
    repo = await _context.law_repo()
    result = await repo.search(query, k)
    if result.is_err():
        return {"error": "search_failed", "reason": result.unwrap_err().message, "sections": []}
    sections: list[dict[str, Any]] = []
    for scored in result.unwrap():
        citation = repo.citation_from_scored(scored)
        section = LawSectionOut.from_citation(citation, amendment_note=citation.amendment_note)
        sections.append(section.model_dump(mode="json"))
    return {"query": query, "sections": sections}


async def verify_citation(claim: str, citation: str) -> dict[str, Any]:
    """Check that a cited section actually exists in the corpus (anti-hallucination)."""
    parsed = _parse_citation(citation)
    if parsed is None:
        return VerificationResult(
            verified=False,
            citation=citation,
            reason="Could not parse a section number from the citation.",
        ).model_dump(mode="json")

    law_code, section_number = parsed
    repo = await _context.law_repo()
    result = await repo.get_section(law_code, section_number)
    if result.is_err():
        return VerificationResult(
            verified=False,
            citation=citation,
            reason=f"Section {section_number} of {law_code.full_title} is not in the corpus.",
        ).model_dump(mode="json")

    found = result.unwrap()
    return VerificationResult(
        verified=True,
        citation=citation,
        reason=(
            "The cited section exists in the corpus. Confirm it supports the claim "
            "using the returned section text."
        ),
        matched_section=LawSectionOut.from_citation(found, amendment_note=found.amendment_note),
    ).model_dump(mode="json")


__all__ = [
    "ToolContext",
    "analyze_contract",
    "search_indian_law",
    "verify_citation",
]
