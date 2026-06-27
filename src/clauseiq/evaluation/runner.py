"""Pytest-compatible evaluation runner.

Runs the live pipeline over the golden dataset, builds a DeepEval ``LLMTestCase``
per case, scores it with the metrics, and aggregates an :class:`EvalReport`. The
deterministic ``CitationAccuracyMetric`` runs on any successful analysis; the
LLM-judged metrics need a working Gemini key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from deepeval.test_case import LLMTestCase

from clauseiq.application.schemas import ContractAnalysis, ContractAnalysisRequest
from clauseiq.application.workflows import ContractAnalyzer
from clauseiq.domain.ports import LawRepository
from clauseiq.domain.value_objects import Jurisdiction
from clauseiq.evaluation.dataset import GoldenCase, GoldenDataset, load_golden_dataset
from clauseiq.evaluation.metrics import CitationAccuracyMetric, GeminiJudge, build_judge_metrics
from clauseiq.infrastructure.llm.factory import LLMRole, get_llm_client
from clauseiq.infrastructure.observability.usage import usage_scope
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

CITATION_ACCURACY = "Citation Accuracy"


def render_analysis(analysis: ContractAnalysis) -> str:
    """Render an analysis as the text DeepEval scores as ``actual_output``."""
    lines = [
        f"Identified {analysis.flag_count} risk flag(s); highest severity: "
        f"{analysis.highest_severity or 'none'}."
    ]
    for flag in analysis.flags:
        citations = "; ".join(citation.reference for citation in flag.citations) or "none"
        lines.append(
            f"- [{flag.severity_label}] {flag.clause_type}: {flag.rationale} (cites: {citations})"
        )
    return "\n".join(lines)


def build_test_case(case: GoldenCase, analysis: ContractAnalysis) -> LLMTestCase:
    """Build a DeepEval test case from a golden case and the produced analysis."""
    citations_meta = [
        {
            "law_code": citation.law_code,
            "section_number": citation.section_number,
            "snippet": citation.snippet,
        }
        for flag in analysis.flags
        for citation in flag.citations
    ]
    retrieval_context = [
        citation.snippet for flag in analysis.flags for citation in flag.citations
    ] or ["(no statutory context retrieved)"]
    return LLMTestCase(
        input=case.contract_text,
        actual_output=render_analysis(analysis),
        expected_output=case.expected_summary,
        retrieval_context=retrieval_context,
        additional_metadata={"citations": citations_meta},
    )


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Per-case evaluation outcome."""

    case_id: str
    ran: bool
    scores: dict[str, float] = field(default_factory=dict)
    cost_usd: float = 0.0
    note: str = ""


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Aggregated evaluation report across the dataset."""

    results: list[CaseResult]

    def metric_means(self) -> dict[str, float]:
        """Mean of each metric across cases that ran (ignoring NaNs)."""
        totals: dict[str, list[float]] = {}
        for result in self.results:
            for name, score in result.scores.items():
                if not math.isnan(score):
                    totals.setdefault(name, []).append(score)
        return {name: sum(values) / len(values) for name, values in totals.items() if values}

    def render(self) -> str:
        """A human-readable summary table."""
        lines = ["=== ClauseIQ Evaluation Report ==="]
        for result in self.results:
            if not result.ran:
                lines.append(f"  {result.case_id}: SKIPPED ({result.note})")
                continue
            scores = ", ".join(f"{name}={score:.2f}" for name, score in result.scores.items())
            lines.append(f"  {result.case_id}: {scores}  [cost ${result.cost_usd:.4f}]")
        means = self.metric_means()
        if means:
            lines.append("--- means ---")
            lines.extend(f"  {name}: {value:.3f}" for name, value in means.items())
        return "\n".join(lines)


async def evaluate_case(
    case: GoldenCase,
    analyzer: ContractAnalyzer,
    citation_metric: CitationAccuracyMetric,
    judge_metrics: list[Any],
) -> CaseResult:
    """Run the pipeline on one case and score it."""
    request = ContractAnalysisRequest(
        contract_text=case.contract_text, jurisdiction=Jurisdiction.IN_MH
    )
    with usage_scope() as usage:
        outcome = await analyzer.analyze(request)
    if outcome.is_err():
        return CaseResult(
            case.id, ran=False, note=f"analysis_failed:{outcome.unwrap_err().message}"
        )

    test_case = build_test_case(case, outcome.unwrap())
    scores: dict[str, float] = {CITATION_ACCURACY: await citation_metric.a_measure(test_case)}
    for metric in judge_metrics:
        name = getattr(metric, "__name__", type(metric).__name__)
        try:
            await metric.a_measure(test_case)
            scores[name] = float(metric.score)
        except Exception as exc:  # a judge failure shouldn't abort the run
            log.warning("metric_failed", metric=name, case=case.id, error=str(exc))
            scores[name] = float("nan")
    return CaseResult(case.id, ran=True, scores=scores, cost_usd=round(usage.cost_usd, 6))


async def evaluate_dataset(
    *,
    analyzer: ContractAnalyzer,
    law_repo: LawRepository,
    dataset: GoldenDataset | None = None,
    include_judge: bool = True,
) -> EvalReport:
    """Evaluate the whole dataset and return a report."""
    cases = (dataset or load_golden_dataset()).cases
    citation_metric = CitationAccuracyMetric(law_repo)
    judge_metrics: list[Any] = []
    if include_judge:
        judge_metrics = build_judge_metrics(GeminiJudge(get_llm_client(LLMRole.ANALYSIS)))
    results = [await evaluate_case(c, analyzer, citation_metric, judge_metrics) for c in cases]
    report = EvalReport(results)
    log.info("evaluation_complete", cases=len(results), means=report.metric_means())
    return report


__all__ = [
    "CITATION_ACCURACY",
    "CaseResult",
    "EvalReport",
    "build_test_case",
    "evaluate_case",
    "evaluate_dataset",
    "render_analysis",
]
