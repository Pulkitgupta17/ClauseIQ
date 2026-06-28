"""Golden dataset schema and loader.

A golden case pairs a contract with the **expected** risk categories, the ICA
sections that should be cited, the rationale themes, and a gold-standard summary,
so the eval harness can score the live pipeline against curated ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clauseiq.domain.exceptions import IngestionError

ContractCategory = Literal["rental", "employment", "nda", "vendor"]

_DEFAULT_PATH = Path(__file__).parent / "golden_dataset.json"


class GoldenCase(BaseModel):
    """A single curated evaluation case."""

    id: str
    category: ContractCategory
    contract_text: str = Field(min_length=100)
    clause_type: list[str] = Field(
        min_length=1, description="Expected risk categories present in the contract."
    )
    expected_sections: list[str] = Field(
        default_factory=list,
        description="ICA sections expected among the citations, e.g. 's.74', 's.27'.",
    )
    key_points: list[str] = Field(
        default_factory=list, description="Rationale themes a good analysis should hit."
    )
    expected_summary: str = Field(
        description="Gold-standard summary of the key risks (DeepEval expected_output)."
    )
    title: str = ""
    notes: str = ""


class GoldenDataset(BaseModel):
    """The full curated dataset."""

    version: str
    cases: list[GoldenCase]

    def by_category(self, category: ContractCategory) -> list[GoldenCase]:
        return [case for case in self.cases if case.category == category]


def normalise_section(reference: str) -> str:
    """Normalise an expected-section label like ``'s.74'`` or ``'ICA s.27'`` to ``'74'``."""
    digits = "".join(char for char in reference if char.isdigit())
    return digits or reference.strip()


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
    "ContractCategory",
    "GoldenCase",
    "GoldenDataset",
    "load_golden_dataset",
    "normalise_section",
]
