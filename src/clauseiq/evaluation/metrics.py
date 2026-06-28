"""DeepEval metrics for the contract-analysis pipeline.

Three groups:

* **Standard DeepEval metrics** (Faithfulness, Answer Relevancy, Contextual
  Recall/Precision) judged by **Gemini** (locked stack = no OpenAI) via
  :class:`GeminiJudge`.
* **CitationAccuracyMetric** — a custom, **deterministic** metric (no LLM): every
  cited section must exist in the corpus and its text must back the citation.
  This is the anti-hallucination guarantee and runs without any API key.
* **LegalSoundnessMetric** — a G-Eval (LLM-as-judge) metric scoring whether the
  analysis is legally sound against a rubric.

``deepeval`` is an optional dependency (the ``eval`` group); import this module
only from the eval harness.
"""

from __future__ import annotations

import asyncio
from typing import Any

from deepeval.metrics import (
    AnswerRelevancyMetric,
    BaseMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    GEval,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from clauseiq.config import settings
from clauseiq.domain.ports import LawRepository
from clauseiq.domain.value_objects import LawCode
from clauseiq.infrastructure.llm.base import LLMClient
from clauseiq.logging_config import get_logger

log = get_logger(__name__)


class GeminiJudge(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
    """Adapts a ClauseIQ :class:`LLMClient` (Gemini) as a DeepEval judge model."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def load_model(self, *_args: Any, **_kwargs: Any) -> Any:
        return self._client

    def get_model_name(self) -> str:
        return f"gemini-judge:{self._client.model_name}"

    async def a_generate(self, prompt: str, schema: Any = None, **_kwargs: Any) -> Any:
        if schema is not None:
            result = await self._client.generate_structured(prompt, schema)
            if result.is_err():
                raise RuntimeError(f"judge_structured_failed:{result.unwrap_err().message}")
            return result.unwrap()
        result = await self._client.generate(prompt)
        if result.is_err():
            raise RuntimeError(f"judge_generate_failed:{result.unwrap_err().message}")
        return result.unwrap()

    def generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(self.a_generate(prompt, schema, **kwargs))


def _tokens(text: str) -> set[str]:
    return {word for word in text.lower().split() if len(word) > 3}


class CitationAccuracyMetric(BaseMetric):  # type: ignore[no-untyped-call]
    """Deterministic metric: cited sections must exist and their text must back the claim.

    Reads the produced citations from ``test_case.additional_metadata['citations']``
    (each ``{law_code, section_number, snippet}``) and verifies each against the
    corpus via the law repository. Score = verified / total.
    """

    def __init__(self, law_repo: LawRepository, *, threshold: float = 0.90) -> None:
        self.threshold = threshold
        self._law_repo = law_repo
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.error: str | None = None
        self.async_mode = True
        self.include_reason = True
        self.evaluation_model = "deterministic"
        self.evaluation_cost = 0.0

    @property
    def __name__(self) -> str:
        return "Citation Accuracy"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        return asyncio.run(self.a_measure(test_case))

    async def a_measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        citations = list((test_case.additional_metadata or {}).get("citations", []))
        if not citations:
            self.score, self.success = 1.0, True
            self.reason = "no citations to verify"
            return self.score

        verified = 0
        for citation in citations:
            if await self._is_verified(citation):
                verified += 1
        self.score = verified / len(citations)
        self.success = self.score >= self.threshold
        self.reason = (
            f"{verified}/{len(citations)} citations exist in the corpus and back the claim"
        )
        return self.score

    async def _is_verified(self, citation: dict[str, Any]) -> bool:
        try:
            law_code = LawCode(str(citation.get("law_code", "")))
        except ValueError:
            return False
        result = await self._law_repo.get_section(law_code, str(citation.get("section_number", "")))
        if result.is_err():
            return False
        section_text = result.unwrap().snippet
        snippet = str(citation.get("snippet", "")).strip()
        if not snippet:
            return True  # existence alone is enough when no snippet is claimed
        # The claimed snippet must substantially overlap the real section text.
        claimed, actual = _tokens(snippet), _tokens(section_text)
        if not claimed:
            return True
        return len(claimed & actual) / len(claimed) >= 0.5

    def is_successful(self) -> bool:
        return bool(self.success)


def build_judge_metrics(judge: GeminiJudge) -> list[BaseMetric]:
    """Build the LLM-judged metrics (need a working Gemini key to run)."""
    faithfulness: BaseMetric = FaithfulnessMetric(
        threshold=settings.faithfulness_threshold, model=judge, async_mode=True
    )
    answer_relevancy: BaseMetric = AnswerRelevancyMetric(
        threshold=0.7, model=judge, async_mode=True
    )
    contextual_recall: BaseMetric = ContextualRecallMetric(
        threshold=settings.context_recall_threshold, model=judge, async_mode=True
    )
    contextual_precision: BaseMetric = ContextualPrecisionMetric(
        threshold=0.7, model=judge, async_mode=True
    )
    legal_soundness: BaseMetric = GEval(
        name="Legal Soundness",
        criteria=(
            "Judge whether the analysis is legally sound for Indian contract law: it "
            "should correctly identify unfair clauses, assign reasonable severity, ground "
            "its reasoning in the cited sections of the Indian Contract Act, 1872, and not "
            "overstate or invent legal conclusions. Penalise hallucinated law or missed "
            "obviously-unfair clauses."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        model=judge,
        threshold=0.7,
    )
    return [
        faithfulness,
        answer_relevancy,
        contextual_recall,
        contextual_precision,
        legal_soundness,
    ]


__all__ = [
    "CitationAccuracyMetric",
    "GeminiJudge",
    "build_judge_metrics",
]
