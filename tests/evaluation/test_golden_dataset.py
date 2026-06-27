"""Evaluation suite (run explicitly: ``uv run pytest tests/evaluation/``).

Excluded from the default test run (it needs the ``eval`` dependency group and,
for the LLM-judged metrics, a working Gemini key). The deterministic
``CitationAccuracyMetric`` runs with neither.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("deepeval")

from deepeval.test_case import LLMTestCase  # noqa: E402

from clauseiq.application.workflows import AnalysisDeps, ContractAnalyzer  # noqa: E402
from clauseiq.config import settings  # noqa: E402
from clauseiq.domain.entities import Citation  # noqa: E402
from clauseiq.domain.exceptions import LawSectionNotFoundError, RepositoryError  # noqa: E402
from clauseiq.domain.result import Err, Ok, Result  # noqa: E402
from clauseiq.domain.value_objects import LawCode  # noqa: E402
from clauseiq.evaluation.metrics import CitationAccuracyMetric  # noqa: E402
from clauseiq.evaluation.runner import evaluate_dataset  # noqa: E402

_SECTION_27_TEXT = (
    "Every agreement by which anyone is restrained from exercising a lawful "
    "profession, trade or business of any kind, is to that extent void."
)


class _FakeLawRepo:
    async def search(
        self, query: str, k: int = 5, *, jurisdiction: object = None
    ) -> Result[list, RepositoryError]:
        return Ok([])

    async def get_section(
        self, law_code: LawCode, section_number: str
    ) -> Result[Citation, RepositoryError]:
        if law_code is LawCode.ICA_1872 and section_number == "27":
            return Ok(
                Citation(
                    law_code=LawCode.ICA_1872,
                    section_number="27",
                    section_title="Agreement in restraint of trade, void",
                    snippet=_SECTION_27_TEXT,
                    effective_date=date(1872, 9, 1),
                )
            )
        return Err(LawSectionNotFoundError("not_found", section=section_number))

    async def count(self) -> int:
        return 1


def _case(citations: list[dict[str, str]]) -> LLMTestCase:
    return LLMTestCase(
        input="x" * 120,
        actual_output="analysis output",
        expected_output="expected",
        additional_metadata={"citations": citations},
    )


async def test_citation_accuracy_scores_real_vs_fabricated() -> None:
    metric = CitationAccuracyMetric(_FakeLawRepo(), threshold=0.90)

    mixed = _case(
        [
            {
                "law_code": "ICA_1872",
                "section_number": "27",
                "snippet": "restrained from exercising a lawful profession is void",
            },
            {"law_code": "ICA_1872", "section_number": "999", "snippet": "fabricated text"},
        ]
    )
    assert await metric.a_measure(mixed) == 0.5
    assert metric.is_successful() is False

    real = _case(
        [
            {
                "law_code": "ICA_1872",
                "section_number": "27",
                "snippet": "restrained from exercising a lawful profession is void",
            }
        ]
    )
    assert await metric.a_measure(real) == 1.0
    assert metric.is_successful() is True


async def test_citation_accuracy_rejects_unfaithful_snippet() -> None:
    metric = CitationAccuracyMetric(_FakeLawRepo(), threshold=0.90)
    # Section 27 exists, but the claimed snippet is unrelated -> not faithful.
    unfaithful = _case(
        [
            {
                "law_code": "ICA_1872",
                "section_number": "27",
                "snippet": "the tenant must repaint the walls annually",
            }
        ]
    )
    assert await metric.a_measure(unfaithful) == 0.0


@pytest.mark.evaluation
async def test_golden_dataset_produces_scored_report() -> None:
    """Full run over the golden dataset; needs real Gemini for LLM-judged metrics."""
    from clauseiq.infrastructure.llm.factory import LLMRole, get_llm_client
    from clauseiq.infrastructure.repositories.law import build_law_repository

    repo = await build_law_repository()
    deps = AnalysisDeps(
        supervisor_llm=get_llm_client(LLMRole.ORCHESTRATION),
        analyzer_llm=get_llm_client(LLMRole.ANALYSIS),
        law_repo=repo,
        corpus_version=settings.corpus_version,
    )
    report = await evaluate_dataset(analyzer=ContractAnalyzer(deps), law_repo=repo)
    print("\n" + report.render())  # the scored report

    ran = [result for result in report.results if result.ran]
    if not ran:
        pytest.skip("no cases ran (Gemini quota unavailable) — report shows skips")
    means = report.metric_means()
    assert means.get("Citation Accuracy", 0.0) >= 0.90
    if "Faithfulness" in means:
        assert means["Faithfulness"] >= settings.faithfulness_threshold
    if "Contextual Recall" in means:
        assert means["Contextual Recall"] >= settings.context_recall_threshold
