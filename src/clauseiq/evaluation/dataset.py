"""Golden dataset schema and loader.

A golden case pairs a contract with the **expected** findings a good analysis
should surface, so the eval harness can score the live pipeline's output against
a curated ground truth. Curators (the human) fill ``contract_text``,
``expected_findings`` and ``expected_summary``; the runner produces the actual
output and the metrics compare.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clauseiq.domain.exceptions import IngestionError

ContractType = Literal["rental", "employment", "nda", "vendor"]

_DEFAULT_PATH = Path(__file__).parent / "golden_dataset.json"


class ExpectedFinding(BaseModel):
    """One risk the analysis is expected to surface for a case."""

    clause_type: str = Field(description="Expected ClauseType value, e.g. 'non_compete'.")
    min_severity: int = Field(ge=1, le=5, description="Lowest acceptable severity (1-5).")
    expected_sections: list[str] = Field(
        default_factory=list,
        description="ICA section numbers expected among the citations, e.g. ['27','74'].",
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Rationale themes the analysis should mention (used by the judge).",
    )


class GoldenCase(BaseModel):
    """A single curated evaluation case."""

    id: str
    contract_type: ContractType
    title: str
    contract_text: str = Field(min_length=100)
    expected_findings: list[ExpectedFinding] = Field(min_length=1)
    expected_summary: str = Field(
        description="Gold-standard summary of the key risks (DeepEval expected_output)."
    )
    notes: str = ""


class GoldenDataset(BaseModel):
    """The full curated dataset."""

    version: str
    cases: list[GoldenCase]

    def by_type(self, contract_type: ContractType) -> list[GoldenCase]:
        return [case for case in self.cases if case.contract_type == contract_type]


def load_golden_dataset(path: Path | None = None) -> GoldenDataset:
    """Load and validate the golden dataset JSON."""
    target = path or _DEFAULT_PATH
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise IngestionError("golden_dataset_read_failed", cause=exc, path=str(target)) from exc
    try:
        return GoldenDataset.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        raise IngestionError("golden_dataset_invalid", cause=exc, path=str(target)) from exc


__all__ = [
    "ContractType",
    "ExpectedFinding",
    "GoldenCase",
    "GoldenDataset",
    "load_golden_dataset",
]
