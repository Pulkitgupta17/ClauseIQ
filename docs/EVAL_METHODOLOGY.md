# Evaluation Methodology

How ClauseIQ measures whether its analysis is *good*, not just whether it runs.
This is the layer most portfolio projects skip.

## What we evaluate, and how

We score the **live pipeline** against a **golden dataset** (curated contracts
with expected findings) using a mix of LLM-judged and deterministic metrics.

| Metric | Type | What it checks | Threshold |
|---|---|---|---|
| **Citation Accuracy** | **Deterministic** | Every cited section exists in the corpus *and* its text backs the citation | **≥ 0.90** |
| Faithfulness | LLM judge (DeepEval) | The analysis doesn't contradict the retrieved law | ≥ 0.85 |
| Contextual Recall | LLM judge | The retrieved law covers what the expected answer needs | ≥ 0.80 |
| Contextual Precision | LLM judge | Retrieved law is relevant (not noise) | ≥ 0.70 |
| Answer Relevancy | LLM judge | The analysis addresses the contract | ≥ 0.70 |
| Legal Soundness | LLM judge (G-Eval rubric) | The legal reasoning is sound; no invented law / missed obvious unfairness | ≥ 0.70 |

**The judge is Gemini, not OpenAI** (`GeminiJudge` wraps our `LLMClient` as a
`DeepEvalBaseLLM`) — staying on the locked stack with zero OpenAI dependency.

## The golden dataset

`src/clauseiq/evaluation/golden_dataset.json` — 20 cases (5 rental, 5
employment, 5 NDA, 5 vendor). Each case pairs a contract with `expected_findings`
(clause type, minimum severity, expected ICA sections, rationale themes) and an
`expected_summary` (the gold answer DeepEval compares against). Schema +
validation in `evaluation/dataset.py`.

## Why a deterministic Citation Accuracy metric?

LLM-judged metrics are themselves fallible. The **anti-hallucination guarantee**
— that every citation points to a real section whose text supports the claim —
must not depend on another LLM's opinion. `CitationAccuracyMetric` checks each
produced citation against the corpus directly (`get_section` + token-overlap of
the claimed snippet vs the real section text). It needs no API key and is the
metric we hold to the highest bar (≥ 0.90). Combined with the **Citation
Verifier agent** (which already drops unverifiable citations at analysis time),
this is a two-layer defence: the pipeline produces only real citations, and the
eval *proves* it.

## Running it

```bash
uv sync --group eval
uv run pytest tests/evaluation/        # runs the suite, prints the scored report
```

The suite is excluded from the default `pytest` run (it needs the eval group and,
for the LLM-judged metrics, a Gemini key). The deterministic metric runs with
neither.

## Baseline results

| Metric | Result | Notes |
|---|---|---|
| **Citation Accuracy** (metric correctness) | **1.00 on real citations; 0.0 on fabricated; 0.0 on unfaithful snippet** | Verified deterministically in `tests/evaluation/` — the metric correctly accepts real citations and rejects fabricated/unfaithful ones. |
| Faithfulness, Recall, Precision, Relevancy, Legal Soundness | **pending** | These need live Gemini judging + a live pipeline run. Currently gated on Google billing (free-tier quota = 0 on the project). The harness runs end-to-end and produces the report the moment a credited key is in `.env`; thresholds above are asserted in `test_golden_dataset_produces_scored_report`. |

> When the Gemini quota is available, this section will be updated with the
> measured means (the runner already computes and logs them via
> `EvalReport.metric_means()`).

## What I'd improve next

- **More cases + adversarial cases** (contracts with subtle/no unfair clauses, to
  test precision and false-positive rate).
- **Regression gating in CI**: fail the build if any threshold drops (the
  `eval` GitHub Actions job, with a budgeted Gemini key).
- **Per-clause expected severities** scored against produced severities (a
  severity-MAE metric) for finer signal than pass/fail.
