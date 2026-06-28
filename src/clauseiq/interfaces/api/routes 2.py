"""HTTP API routes (``/api/v1`` + ``/healthz``).

* ``POST /api/v1/analyze`` — analyze a contract, return the full result.
* ``POST /api/v1/analyze/stream`` — analyze with Server-Sent Events, one event
  per agent so the UI can show live progress.
* ``GET /api/v1/law/{section_id}`` — fetch a statutory section (citation
  drill-down). ``section_id`` is ``"<LAW_CODE>:<number>"`` (e.g. ``ICA_1872:27``)
  or a bare number (defaults to the Indian Contract Act).
* ``GET /healthz`` — liveness.

SSE is written by hand (``StreamingResponse`` + ``text/event-stream``) to avoid
an extra dependency; each event is ``event: <name>\\ndata: <json>\\n\\n``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from clauseiq.application.schemas import (
    ContractAnalysis,
    ContractAnalysisRequest,
    LawSectionOut,
)
from clauseiq.application.workflows import ContractAnalyzer
from clauseiq.domain.exceptions import GuardrailError
from clauseiq.domain.ports import LawRepository
from clauseiq.domain.value_objects import LawCode
from clauseiq.interfaces.api.dependencies import get_contract_analyzer, get_law_repository
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter()

AnalyzerDep = Annotated[ContractAnalyzer, Depends(get_contract_analyzer)]
LawRepoDep = Annotated[LawRepository, Depends(get_law_repository)]


def _parse_section_id(section_id: str) -> tuple[LawCode, str]:
    """Parse ``"<LAW_CODE>:<number>"`` (or a bare number) into a code + section."""
    if ":" in section_id:
        code_part, _, number = section_id.partition(":")
        try:
            law_code = LawCode(code_part.strip())
        except ValueError:
            law_code = LawCode.OTHER
        return law_code, number.strip()
    return LawCode.ICA_1872, section_id.strip()


@router.post("/api/v1/analyze", response_model=ContractAnalysis, tags=["analysis"])
async def analyze(request: ContractAnalysisRequest, analyzer: AnalyzerDep) -> ContractAnalysis:
    """Analyze a contract and return structured risk flags with verified citations."""
    result = await analyzer.analyze(request)
    if result.is_err():
        error = result.unwrap_err()
        if isinstance(error, GuardrailError):
            raise HTTPException(
                status_code=422,
                detail={"error": "rejected", "reason": error.message, **error.context},
            )
        status = 503 if "api_key" in error.message else 502
        raise HTTPException(
            status_code=status, detail={"error": "analysis_failed", "reason": error.message}
        )
    return result.unwrap()


@router.post("/api/v1/analyze/stream", tags=["analysis"])
async def analyze_stream(
    request: ContractAnalysisRequest, analyzer: AnalyzerDep
) -> StreamingResponse:
    """Analyze a contract, streaming one SSE event as each agent completes."""

    async def event_source() -> AsyncIterator[str]:
        async for event in analyzer.stream(request):
            yield f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/v1/law/{section_id}", response_model=LawSectionOut, tags=["law"])
async def get_law_section(section_id: str, law_repo: LawRepoDep) -> LawSectionOut:
    """Fetch a single statutory section for citation drill-down."""
    law_code, section_number = _parse_section_id(section_id)
    result = await law_repo.get_section(law_code, section_number)
    if result.is_err():
        raise HTTPException(
            status_code=404, detail={"error": "section_not_found", "section_id": section_id}
        )
    citation = result.unwrap()
    return LawSectionOut.from_citation(citation, amendment_note=citation.amendment_note)


@router.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe (k8s-style)."""
    return {"status": "ok"}


__all__ = ["router"]
