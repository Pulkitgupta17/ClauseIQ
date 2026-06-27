"""Unit tests for the golden-dataset schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauseiq.domain.exceptions import IngestionError
from clauseiq.evaluation.dataset import GoldenDataset, load_golden_dataset


def test_bundled_golden_dataset_is_valid() -> None:
    dataset = load_golden_dataset()
    assert dataset.version
    ids = {case.id for case in dataset.cases}
    assert {"rental-01", "employment-01"} <= ids
    # Every case has at least one expected finding with a valid severity.
    for case in dataset.cases:
        assert case.expected_findings
        for finding in case.expected_findings:
            assert 1 <= finding.min_severity <= 5


def test_by_type_filters() -> None:
    dataset = load_golden_dataset()
    assert all(c.contract_type == "rental" for c in dataset.by_type("rental"))


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


def test_dataset_model_roundtrip() -> None:
    dataset = load_golden_dataset()
    assert GoldenDataset.model_validate_json(dataset.model_dump_json()).version == dataset.version
