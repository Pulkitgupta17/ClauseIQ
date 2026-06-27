"""Unit tests for application schemas, severity mapping, and converters."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from clauseiq.application.schemas import (
    AnalyzedFlag,
    CitationOut,
    ContractAnalysis,
    RiskFlagOut,
    coerce_clause_type,
)
from clauseiq.domain.entities import Citation, RiskFlag
from clauseiq.domain.exceptions import ValidationError
from clauseiq.domain.value_objects import ClauseType, Jurisdiction, LawCode, Severity


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1, Severity.INFO),
        (2, Severity.LOW),
        (3, Severity.MEDIUM),
        (4, Severity.HIGH),
        (5, Severity.CRITICAL),
    ],
)
def test_severity_from_score(score: int, expected: Severity) -> None:
    assert Severity.from_score(score) is expected
    assert expected.score == score


@pytest.mark.parametrize("score", [0, 6, -1])
def test_severity_from_score_rejects_out_of_range(score: int) -> None:
    with pytest.raises(ValidationError):
        Severity.from_score(score)


def test_coerce_clause_type() -> None:
    assert coerce_clause_type("LOCK_IN") is ClauseType.LOCK_IN
    assert coerce_clause_type("arbitration") is ClauseType.ARBITRATION
    assert coerce_clause_type("something the llm invented") is ClauseType.OTHER


def test_analyzed_flag_rejects_out_of_range_severity() -> None:
    with pytest.raises(PydanticValidationError):
        AnalyzedFlag(
            clause_index=0, clause_type="lock_in", severity_score=7, rationale="x", confidence=0.5
        )
    with pytest.raises(PydanticValidationError):
        AnalyzedFlag(
            clause_index=0, clause_type="lock_in", severity_score=3, rationale="x", confidence=1.5
        )


def _citation() -> Citation:
    return Citation(
        law_code=LawCode.ICA_1872,
        section_number="27",
        section_title="Agreement in restraint of trade, void",
        snippet="Every agreement by which anyone is restrained ... is void.",
        effective_date=date(1872, 9, 1),
    )


def test_citation_out_from_domain_carries_amendment_note() -> None:
    out = CitationOut.from_domain(_citation(), amendment_note="not tracked")
    assert out.reference == "Section 27, Indian Contract Act, 1872"
    assert out.amendment_note == "not tracked"
    assert out.law_code == "ICA_1872"


def test_risk_flag_out_exposes_score_and_label() -> None:
    flag = RiskFlag(
        clause_id="c1",
        clause_type=ClauseType.NON_COMPETE,
        severity=Severity.HIGH,
        rationale="Restraint of trade is void under s.27.",
        confidence=0.9,
    )
    out = RiskFlagOut.from_domain(
        flag,
        clause_excerpt="Employee shall not work in the industry for 2 years.",
        clause_heading="12. Non-compete",
        citations=[CitationOut.from_domain(_citation())],
    )
    assert out.severity_score == 4
    assert out.severity_label == "high"
    assert out.clause_type == "non_compete"
    assert out.citations[0].section_number == "27"


def test_contract_analysis_build_computes_highest_severity() -> None:
    flags = [
        RiskFlagOut(
            clause_id="c1",
            clause_excerpt="x",
            clause_type="lock_in",
            severity_score=2,
            severity_label="low",
            rationale="r",
            confidence=0.5,
        ),
        RiskFlagOut(
            clause_id="c2",
            clause_excerpt="y",
            clause_type="non_compete",
            severity_score=5,
            severity_label="critical",
            rationale="r",
            confidence=0.8,
        ),
    ]
    analysis = ContractAnalysis.build(
        contract_id="k1",
        jurisdiction=Jurisdiction.IN_MH,
        flags=flags,
        corpus_version="ICA-1872-indiacode-2026-06-25",
        disclaimer="not legal advice",
    )
    assert analysis.flag_count == 2
    assert analysis.highest_severity == "critical"
    assert analysis.jurisdiction == "IN-MH"
