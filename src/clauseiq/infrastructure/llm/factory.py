"""LLM client factory — selects a client by role (Factory pattern).

Keeps the rest of the system free of model-name strings: agents ask for a *role*
(orchestration or analysis) and get the right Gemini client. Swapping models or
providers happens here, behind the :class:`LLMClient` port.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from clauseiq.infrastructure.llm.base import LLMClient
from clauseiq.infrastructure.llm.gemini_flash import GeminiFlashClient
from clauseiq.infrastructure.llm.gemini_pro import GeminiProClient


class LLMRole(str, Enum):
    """The role an LLM plays, decoupled from the concrete model."""

    ORCHESTRATION = "orchestration"  # fast routing/segmentation -> Gemini Flash
    ANALYSIS = "analysis"  # heavy reasoning -> Gemini Pro


def get_llm_client(role: LLMRole, *, api_key: str | None = None, client: Any = None) -> LLMClient:
    """Return the LLM client for ``role``.

    Args:
        role: Which capability is needed.
        api_key: Optional key override (else ``settings.gemini_api_key``).
        client: Optional injected SDK client (for testing).
    """
    if role is LLMRole.ORCHESTRATION:
        return GeminiFlashClient(api_key=api_key, client=client)
    if role is LLMRole.ANALYSIS:
        return GeminiProClient(api_key=api_key, client=client)
    raise ValueError(f"unknown LLM role: {role!r}")  # pragma: no cover - exhaustive enum


__all__ = ["LLMRole", "get_llm_client"]
