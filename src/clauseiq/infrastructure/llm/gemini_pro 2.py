"""Gemini 2.5 Pro adapter — the stronger model used for analysis.

Used by the Risk Analyzer for the reasoning-heavy step: judging whether clauses
are unfair, assigning severity with justification, and proposing citations.
Configured from ``settings.analysis_model``.
"""

from __future__ import annotations

from typing import Any

from clauseiq.config import settings
from clauseiq.infrastructure.llm.base import GeminiClient


class GeminiProClient(GeminiClient):
    """Gemini Pro client for analysis tasks."""

    def __init__(self, *, api_key: str | None = None, client: Any = None) -> None:
        super().__init__(settings.analysis_model, api_key=api_key, client=client)


__all__ = ["GeminiProClient"]
