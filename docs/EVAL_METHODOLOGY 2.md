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

Full 20-case run (5 each: rental, employment, NDA, vendor), Gemini as judge:

| Metric | Score | Role |
|---|---|---|
| **Citation Accuracy** | **1.00** | **gate** (≥ 0.90) |
| **Faithfulness** | **0.90** | **gate** (≥ 0.85) |
| Answer Relevancy | 0.90 | informational |
| Legal Soundness (G-Eval) | 0.82 | informational |
| Contextual Precision | 0.57 | informational |
| Contextual Recall | 0.26 | informational (see below) |

**Cost:** ~$0.007 per contract (avg over 20 cases; range $0.0034–$0.0190).

### Why Contextual Recall is informational, not a gate

DeepEval's Contextual Recall measures how much of the **expected output** (our gold
*summary*) is attributable to the **retrieval context**. We populate the retrieval
context with the *raw statute snippets* that were cited — but the gold summary
states legal *conclusions* ("void under s.28") that aren't verbatim in the statute,
so the metric structurally understates recall. Crucially, this is **not** a
retrieval failure: Citation Accuracy is a perfect 1.00 and Faithfulness is 0.90,
which would be impossible if the retriever were missing the relevant law. So we
gate on Citation Accuracy + Faithfulness and report Recall/Precision for insight.
A cleaner fix (future work) is to feed the full retrieved law pool — not just the
final citations — as the retrieval context.

## What I'd improve next

- **More cases + adversarial cases** (contracts with subtle/no unfair clauses, to
  test precision and false-positive rate).
- **Regression gating in CI**: fail the build if any threshold drops (the
  `eval` GitHub Actions job, with a budgeted Gemini key).
- **Per-clause expected severities** scored against produced severities (a
  severity-MAE metric) for finer signal than pass/fail.
