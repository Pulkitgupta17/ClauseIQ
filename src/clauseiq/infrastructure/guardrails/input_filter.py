"""Input guardrail — reject documents that are not contracts.

A cheap, deterministic first gate (before any LLM call): score the text for
contract-like signals and against obvious non-contract signals (e.g. a recipe).
The supervisor agent's LLM ``is_contract`` check is the second, smarter layer;
this one rejects junk for free and gives a clear, fast error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that strongly indicate a contract/agreement.
_CONTRACT_SIGNALS = frozenset(
    {
        "agreement",
        "contract",
        "party",
        "parties",
        "hereby",
        "shall",
        "herein",
        "whereas",
        "clause",
        "terms",
        "conditions",
        "obligations",
        "liability",
        "indemnify",
        "indemnity",
        "terminate",
        "termination",
        "breach",
        "covenant",
        "warranty",
        "jurisdiction",
        "arbitration",
        "governing",
        "consideration",
        "tenant",
        "landlord",
        "lessor",
        "lessee",
        "lease",
        "rent",
        "deposit",
        "employee",
        "employer",
        "employment",
        "salary",
        "confidential",
        "disclosing",
        "receiving",
        "vendor",
        "supplier",
        "services",
        "payment",
    }
)

# Words that strongly indicate the document is something else (recipe, article…).
_NON_CONTRACT_SIGNALS = frozenset(
    {
        "ingredients",
        "teaspoon",
        "tablespoon",
        "preheat",
        "oven",
        "bake",
        "recipe",
        "servings",
        "cup",
        "cups",
        "whisk",
        "simmer",
        "garnish",
        "chapter",
        "verse",
        "lyrics",
        "chorus",
        "stanza",
        "abstract",
        "doi",
    }
)

_WORD_RE = re.compile(r"[a-z]+")

# Tuning: a contract should have several distinct signal terms and a non-trivial
# signal density; junk has near-zero. These are deliberately lenient (avoid false
# rejects) — the LLM layer catches subtler non-contracts.
_MIN_WORDS = 30
_MIN_DISTINCT_SIGNALS = 3
_MIN_SIGNAL_DENSITY = 0.015


@dataclass(frozen=True, slots=True)
class InputAssessment:
    """Result of screening an input document."""

    accepted: bool
    reason: str
    signal_score: float
    distinct_signals: int


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def screen_input(text: str) -> InputAssessment:
    """Assess whether ``text`` looks like a contract.

    Returns an :class:`InputAssessment`; ``accepted=False`` with a human-readable
    ``reason`` when the document should be rejected.
    """
    words = _tokens(text)
    total = len(words)
    if total < _MIN_WORDS:
        return InputAssessment(False, "document_too_short", 0.0, 0)

    word_set = set(words)
    contract_hits = word_set & _CONTRACT_SIGNALS
    non_contract_hits = word_set & _NON_CONTRACT_SIGNALS
    signal_count = sum(1 for w in words if w in _CONTRACT_SIGNALS)
    density = signal_count / total
    distinct = len(contract_hits)

    # Clearly a different kind of document (more non-contract than contract signals).
    if len(non_contract_hits) >= 3 and len(non_contract_hits) > distinct:
        return InputAssessment(False, "looks_like_non_contract_document", density, distinct)

    if distinct < _MIN_DISTINCT_SIGNALS or density < _MIN_SIGNAL_DENSITY:
        return InputAssessment(False, "insufficient_contract_signals", density, distinct)

    return InputAssessment(True, "accepted", density, distinct)


__all__ = ["InputAssessment", "screen_input"]
