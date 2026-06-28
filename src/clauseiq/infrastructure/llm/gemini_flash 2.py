"""Gemini 2.0 Flash adapter — the fast, cheap model used for orchestration.

Used by the supervisor for input triage, clause segmentation, and deriving
retrieval queries: high-volume, latency-sensitive steps where Flash's speed and
generous free-tier limits fit. Configured from ``settings.orchestration_model``.
"""

from __future__ import annotations

from typing import Any

from clauseiq.config import settings
from clauseiq.infrastructure.llm.base import GeminiClient


class GeminiFlashClient(GeminiClient):
    """Gemini Flash client for orchestration tasks."""

    def __init__(self, *, api_key: str | None = None, client: Any = None) -> None:
        super().__init__(settings.orchestration_model, api_key=api_key, client=client)


__all__ = ["GeminiFlashClient"]
