"""Core domain entities for ClauseIQ.

Entities are modelled as **frozen** dataclasses: they are immutable value
carriers compared by value, with no behaviour that reaches outside the domain.
Immutability makes them safe to pass between concurrent agents and trivial to
reason about in tests.

Invariants are enforced in ``__post_init__`` and raise
:class:`~clauseiq.domain.exceptions.ValidationError` on violation, so an invalid
entity can never be constructed.

Note on hashing: entities that carry a ``metadata`` mapping are compared by
value but are not hashable (a mapping field is mutable); they are not intended
to be used as set members or dict keys.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from clauseiq.domain.exceptions import ValidationError
from clauseiq.domain.value_objects import ClauseType, Jurisdiction, LawCode, Severity


def _require(condition: bool, message: str, **context: object) -> None:
    """Raise :class:`ValidationError` (with structured context) when false.

    Context is attached after construction rather than forwarded as ``**context``
    so it can never collide with the reserved ``code``/``cause`` keyword
    arguments of :class:`ClauseIQError`.
    """
    if not condition:
        error = ValidationError(message)
        error.context.update(context)
        raise error


def _require_unit_interval(name: str, value: float | None) -> None:
    """Validate that an optional score lies in the inclusive interval [0, 1]."""
    if value is None:
        return
    if not math.isfinite(value) or not (0.0 <= value <= 1.0):
        error = ValidationError(f"{name} must be within [0.0, 1.0]")
        error.context[name] = value
        raise error


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable unit of text plus provenance metadata.

    Produced by the chunker (for contracts) and the law ingestor (for statutory
    sections), and stored in / returned from the vector store.

    Attributes:
        id: Stable, unique identifier for this chunk (used as the vector-store
            primary key).
        text: The chunk's textual content.
        metadata: String-valued provenance (e.g. ``law_code``, ``section``,
            ``parent_section``). Constrained to strings because vector-store
            metadata filters operate on scalar values.
    """

    id: str
    text: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(bool(self.id.strip()), "Chunk.id must be non-empty")
        _require(bool(self.text.strip()), "Chunk.text must be non-empty", chunk_id=self.id)


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A :class:`Chunk` paired with a relevance score from a retriever.

    The score's scale depends on the producing strategy (BM25 vs cosine vs RRF);
    consumers should treat it as monotonic (higher = more relevant) rather than
    absolute.
    """

    chunk: Chunk
    score: float

    def __post_init__(self) -> None:
        _require(
            math.isfinite(self.score),
            "ScoredChunk.score must be finite",
            chunk_id=self.chunk.id,
            score=self.score,
        )


@dataclass(frozen=True, slots=True)
class Citation:
    """A reference to a specific section of Indian law backing a risk flag.

    Carries corpus-freshness fields (:attr:`effective_date`,
    :attr:`last_amended`, :attr:`source_fetched_at`) so the UI can tell users
    *when* the cited law was last updated and when our copy was fetched — a
    deliberate guardrail for time-sensitive legal matters.
    """

    law_code: LawCode
    section_number: str
    section_title: str
    snippet: str
    source_url: str | None = None
    effective_date: date | None = None
    last_amended: date | None = None
    source_fetched_at: date | None = None
    relevance_score: float | None = None

    def __post_init__(self) -> None:
        _require(bool(self.section_number.strip()), "Citation.section_number must be non-empty")
        _require(bool(self.snippet.strip()), "Citation.snippet must be non-empty")
        _require_unit_interval("relevance_score", self.relevance_score)

    @property
    def reference(self) -> str:
        """Human-facing citation label, e.g. ``"Section 23, Indian Contract Act, 1872"``."""
        return f"Section {self.section_number}, {self.law_code.full_title}"


@dataclass(frozen=True, slots=True)
class Clause:
    """A single clause extracted from a contract.

    ``clause_type`` is ``None`` until the Risk Analyzer classifies it, keeping
    extraction (ingestion) and classification (analysis) cleanly separated.
    """

    id: str
    text: str
    ordinal: int
    heading: str | None = None
    clause_type: ClauseType | None = None
    char_start: int | None = None
    char_end: int | None = None

    def __post_init__(self) -> None:
        _require(bool(self.id.strip()), "Clause.id must be non-empty")
        _require(bool(self.text.strip()), "Clause.text must be non-empty", clause_id=self.id)
        _require(self.ordinal >= 0, "Clause.ordinal must be non-negative", clause_id=self.id)


@dataclass(frozen=True, slots=True)
class RiskFlag:
    """A flagged risk on a clause: its severity, rationale, and legal backing."""

    clause_id: str
    clause_type: ClauseType
    severity: Severity
    rationale: str
    citations: tuple[Citation, ...] = ()
    confidence: float = 0.0
    suggested_action: str | None = None

    def __post_init__(self) -> None:
        _require(bool(self.clause_id.strip()), "RiskFlag.clause_id must be non-empty")
        _require(bool(self.rationale.strip()), "RiskFlag.rationale must be non-empty")
        _require_unit_interval("confidence", self.confidence)


@dataclass(frozen=True, slots=True)
class Contract:
    """A contract under analysis: its raw text and extracted clauses."""

    id: str
    raw_text: str
    clauses: tuple[Clause, ...] = ()
    jurisdiction: Jurisdiction = Jurisdiction.IN_MH
    title: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(bool(self.id.strip()), "Contract.id must be non-empty")
        _require(
            bool(self.raw_text.strip()), "Contract.raw_text must be non-empty", contract_id=self.id
        )


__all__ = [
    "Chunk",
    "Citation",
    "Clause",
    "Contract",
    "RiskFlag",
    "ScoredChunk",
]
