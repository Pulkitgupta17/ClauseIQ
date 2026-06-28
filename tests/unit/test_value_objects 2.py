"""Unit tests for domain value objects (enums)."""

from __future__ import annotations

from clauseiq.domain.value_objects import ClauseType, Jurisdiction, LawCode, Severity


def test_severity_is_ordered() -> None:
    assert Severity.INFO < Severity.LOW < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL
    assert max(Severity) is Severity.CRITICAL
    assert sorted([Severity.HIGH, Severity.INFO, Severity.CRITICAL]) == [
        Severity.INFO,
        Severity.HIGH,
        Severity.CRITICAL,
    ]


def test_severity_label_and_normalized_score() -> None:
    assert Severity.CRITICAL.label == "critical"
    assert Severity.INFO.normalized_score == 0.0
    assert Severity.CRITICAL.normalized_score == 1.0
    assert 0.0 < Severity.MEDIUM.normalized_score < 1.0


def test_clause_type_serialises_to_string() -> None:
    assert ClauseType.SECURITY_DEPOSIT.value == "security_deposit"
    # str-enum members are usable directly as strings
    assert ClauseType.ARBITRATION == "arbitration"
    assert ClauseType("non_compete") is ClauseType.NON_COMPETE


def test_jurisdiction_values_match_api_contract() -> None:
    assert {j.value for j in Jurisdiction} == {"IN-MH", "IN-DL", "IN-KA"}
    assert Jurisdiction.IN_MH.state_name == "Maharashtra"
    assert Jurisdiction("IN-KA").state_name == "Karnataka"


def test_law_code_titles_are_present_for_all_members() -> None:
    for code in LawCode:
        assert code.full_title  # non-empty canonical title
    assert LawCode.ICA_1872.full_title == "Indian Contract Act, 1872"
