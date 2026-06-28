"""Unit tests for the golden-dataset schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauseiq.domain.exceptions import IngestionError
from clauseiq.evaluation.dataset import GoldenDataset, load_golden_dataset, normalise_section


def test_bundled_dataset_has_20_balanced_cases() -> None:
    dataset = load_golden_dataset()
    assert dataset.version
    assert len(dataset.cases) == 20
    for category in ("rental", "employment", "nda", "vendor"):
        assert len(dataset.by_category(category)) == 5  # type: ignore[arg-type]


def test_every_case_is_well_formed() -> None:
    for case in load_golden_dataset().cases:
        assert len(case.contract_text) >= 100
        assert case.clause_type  # at least one expected risk category
        assert case.expected_summary
        assert case.id


def test_seed_cases_present() -> None:
    ids = {case.id for case in load_golden_dataset().cases}
    assert {"rental_001", "employment_001"} <= ids


@pytest.mark.parametrize(
    ("reference", "expected"),
    [("s.74", "74"), ("ICA s.27", "27"), ("28", "28"), ("Section 23", "23")],
)
def test_normalise_section(reference: str, expected: str) -> None:
    assert normalise_section(reference) == expected


def test_loader_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(IngestionError):
        load_golden_dataset(bad)


def test_loader_rejects_schema_violation(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"version": "x", "cases": [{"id": "a"}]}), encoding="utf-8")
    with pytest.raises(IngestionError):
        load_golden_dataset(wrong)


def test_dataset_roundtrip() -> None:
    dataset = load_golden_dataset()
    assert GoldenDataset.model_validate_json(dataset.model_dump_json()).version == dataset.version
