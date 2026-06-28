"""Output guardrail — guarantee the legal disclaimer is attached.

ClauseIQ is decision-support, not legal advice. Every analysis that leaves the
system must carry the disclaimer, regardless of which code path built it, so this
is enforced once here rather than trusted to each producer.
"""

from __future__ import annotations

from clauseiq.application.schemas import ContractAnalysis

LEGAL_DISCLAIMER = (
    "ClauseIQ provides automated decision-support, not legal advice. It cites the "
    "Indian Contract Act, 1872; amendment history is not tracked. Consult a "
    "qualified lawyer and verify current law before acting on this analysis."
)


def ensure_disclaimer(analysis: ContractAnalysis) -> ContractAnalysis:
    """Return ``analysis`` with a non-empty disclaimer guaranteed."""
    if analysis.disclaimer and analysis.disclaimer.strip():
        return analysis
    return analysis.model_copy(update={"disclaimer": LEGAL_DISCLAIMER})


def append_disclaimer(text: str) -> str:
    """Append the disclaimer to a plain-text output."""
    return f"{text.rstrip()}\n\n---\n{LEGAL_DISCLAIMER}"


__all__ = ["LEGAL_DISCLAIMER", "append_disclaimer", "ensure_disclaimer"]
