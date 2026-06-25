"""Unit tests for domain entities and their invariants."""

from __future__ import annotations

from datetime import date

import pytest

from clauseiq.domain.entities import (
    Chunk,
    Citation,
    Clause,
    Contract,
    RiskFlag,
    ScoredChunk,
)
from clauseiq.domain.exceptions import ValidationError
from clauseiq.domain.value_objects import ClauseType, Jurisdiction, LawCode, Severity


def test_chunk_valid_and_immutable() -> None:
    chunk = Chunk(id="c1", text="hello", metadata={"law_code": "ICA_1872"})
    assert chunk.text == "hello"
    assert chunk.metadata["law_code"] == "ICA_1872"
    with pytest.raises((AttributeError, TypeError)):
        chunk.text = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("chunk_id", "text"),
    [("", "text"), ("  ", "text"), ("c1", ""), ("c1", "   ")],
)
def test_chunk_rejects_empty_fields(chunk_id: str, text: str) -> None:
    with pytest.raises(ValidationError):
        Chunk(id=chunk_id, text=text)


def test_scored_chunk_rejects_non_finite_score() -> None:
    chunk = Chunk(id="c1", text="hello")
    assert ScoredChunk(chunk=chunk, score=0.5).score == 0.5
    with pytest.raises(ValidationError):
        ScoredChunk(chunk=chunk, score=float("nan"))


def test_citation_reference_and_freshness_fields() -> None:
    citation = Citation(
        law_code=LawCode.ICA_1872,
        section_number="23",
        section_title="What considerations and objects are lawful",
        snippet="The consideration or object of an agreement is lawful, unless...",
        effective_date=date(1872, 9, 1),
        last_amended=date(2018, 1, 1),
        source_fetched_at=date(2026, 6, 25),
        relevance_score=0.91,
    )
    assert citation.reference == "Section 23, Indian Contract Act, 1872"
    assert citation.source_fetched_at == date(2026, 6, 25)


def test_citation_defaults_have_no_freshness() -> None:
    citation = Citation(
        law_code=LawCode.ICA_1872,
        section_number="10",
        section_title="What agreements are contracts",
        snippet="All agreements are contracts if they are made by free consent...",
    )
    assert citation.effective_date is None
    assert citation.last_amended is None
    assert citation.source_fetched_at is None
    assert citation.relevance_score is None


def test_citation_rejects_out_of_range_relevance() -> None:
    with pytest.raises(ValidationError):
        Citation(
            law_code=LawCode.ICA_1872,
            section_number="10",
            section_title="t",
            snippet="s",
            relevance_score=1.5,
        )


def test_clause_optional_classification() -> None:
    clause = Clause(id="cl1", text="The tenant shall...", ordinal=0)
    assert clause.clause_type is None
    classified = Clause(
        id="cl1", text="The tenant shall...", ordinal=0, clause_type=ClauseType.LOCK_IN
    )
    assert classified.clause_type is ClauseType.LOCK_IN


def test_clause_rejects_negative_ordinal() -> None:
    with pytest.raises(ValidationError):
        Clause(id="cl1", text="x", ordinal=-1)


def test_risk_flag_validates_confidence() -> None:
    flag = RiskFlag(
        clause_id="cl1",
        clause_type=ClauseType.LOCK_IN,
        severity=Severity.HIGH,
        rationale="Lock-in of 11 months is unconscionable for a 12-month lease.",
        confidence=0.8,
    )
    assert flag.severity is Severity.HIGH
    with pytest.raises(ValidationError):
        RiskFlag(
            clause_id="cl1",
            clause_type=ClauseType.LOCK_IN,
            severity=Severity.HIGH,
            rationale="x",
            confidence=2.0,
        )


def test_contract_defaults_and_validation() -> None:
    contract = Contract(id="k1", raw_text="This agreement is made...")
    assert contract.jurisdiction is Jurisdiction.IN_MH
    assert contract.clauses == ()
    with pytest.raises(ValidationError):
        Contract(id="k1", raw_text="   ")
