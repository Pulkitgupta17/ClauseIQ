"""Token usage and cost accounting.

A :class:`UsageTotals` accumulator lives in a context variable for the duration
of an analysis; the LLM client records each call's tokens into it, and the
``@traced`` decorator reads before/after snapshots to attribute tokens and
``cost_usd`` to individual agent nodes. Cost is computed from a per-model price
table (USD per million tokens, input/output).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

# USD per 1M tokens, (input, output). Gemini API list prices.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.0),
}
# Fallback for unknown models: assume the cheap flash tier.
_DEFAULT_PRICING = (0.10, 0.40)


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost of a call given its model and token counts."""
    input_rate, output_rate = _PRICING_PER_MTOK.get(model, _DEFAULT_PRICING)
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000


@dataclass
class UsageTotals:
    """Running totals of token usage and cost."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add one call's usage to the totals."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.cost_usd += cost_for(model, prompt_tokens, completion_tokens)

    def snapshot(self) -> UsageTotals:
        """Return an immutable copy of the current totals."""
        return UsageTotals(
            self.prompt_tokens, self.completion_tokens, self.total_tokens, self.cost_usd
        )

    def since(self, earlier: UsageTotals) -> UsageTotals:
        """Return the delta of these totals relative to an earlier snapshot."""
        return UsageTotals(
            self.prompt_tokens - earlier.prompt_tokens,
            self.completion_tokens - earlier.completion_tokens,
            self.total_tokens - earlier.total_tokens,
            round(self.cost_usd - earlier.cost_usd, 8),
        )


_usage_var: ContextVar[UsageTotals | None] = ContextVar("usage_totals", default=None)


def record_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Record a call's usage into the active accumulator (no-op if none)."""
    totals = _usage_var.get()
    if totals is not None:
        totals.record(model, prompt_tokens, completion_tokens)


def current_usage() -> UsageTotals | None:
    """Return the active usage accumulator, if any."""
    return _usage_var.get()


@contextmanager
def usage_scope() -> Iterator[UsageTotals]:
    """Install a fresh usage accumulator for the duration of the block."""
    totals = UsageTotals()
    token = _usage_var.set(totals)
    try:
        yield totals
    finally:
        _usage_var.reset(token)


__all__ = [
    "UsageTotals",
    "cost_for",
    "current_usage",
    "record_usage",
    "usage_scope",
]
