# Component: Quality Layer (Guardrails, Observability, Eval)

**Files:** `infrastructure/guardrails/*`, `infrastructure/observability/*`,
`evaluation/*`
**Tests:** `tests/unit/test_guardrails.py`, `test_usage.py`,
`test_observability.py`, `tests/evaluation/`

This is the "production-grade" layer that separates a demo from a real system:
safety, traceability, and measured quality. See also `docs/EVAL_METHODOLOGY.md`.

## 1. Guardrails (`infrastructure/guardrails/`)

Cheap, deterministic checks around the expensive LLM pipeline, wired into
`ContractAnalyzer` so both API and MCP enforce them.

- **`input_filter`** — scores the document for contract signals vs non-contract
  signals (recipe/article words); rejects junk (`not_a_contract`) before any LLM
  call. The supervisor's LLM `is_contract` check is the smarter second layer.
- **`injection_detector`** — flags prompt-injection attempts ("ignore previous
  instructions", `</system>`, …) using **specific** patterns chosen to *not* fire
  on ordinary legalese ("the agent shall act as…"). Detection → `GuardrailError`.
- **`output_filter`** — guarantees the legal disclaimer is attached to every
  result, enforced in one place rather than trusted to each producer.

Rejections surface as `GuardrailError` → **HTTP 422** (API) or `{"error": …}` (MCP).

## 2. Observability (`infrastructure/observability/`)

**Token/cost accounting + Langfuse tracing**, capturing the fields a real system
needs to debug and bill.

- **`usage`** — a `UsageTotals` accumulator in a context variable. The Gemini
  client records each call's `usage_metadata` into it; `cost_usd` is computed
  from a per-model price table (Flash $0.10/$0.40, Pro $1.25/$10 per MTok).
- **`@traced(name)`** — wraps every agent node and MCP tool. On completion it
  records `trace_id`, `agent_name`, `latency_ms`, `tokens_used`, `cost_usd`:
  - **always** to structlog (so cost is logged and visible per request even with
    no Langfuse), and
  - to **Langfuse** (one trace per analysis, a span per node) when keys are
    configured — best-effort and guarded so tracing never breaks an analysis.
- **Cost per analysis** is logged (`analysis_complete`) and returned in the SSE
  `done` event's `usage` field.

The `trace_id` ties it together: API middleware sets it per request; `ensure_trace`
reuses it (or creates one for MCP/scripts) so every node/tool/log line in one
analysis shares an id.

## 3. Evaluation (`evaluation/`)

See `docs/EVAL_METHODOLOGY.md` for the full story. In short: a golden dataset, a
**Gemini-judged** DeepEval metric suite, and a **deterministic
`CitationAccuracyMetric`** (the anti-hallucination guarantee, ≥ 0.90, no API key),
run by a `runner` that scores the live pipeline and renders a report.

## Likely interview questions

**Q: How do you stop prompt injection in a tool that feeds user text to an LLM?**
A: Two layers. A deterministic detector rejects obvious injection patterns before
the LLM sees the text (tuned to avoid false positives on legal language), and the
structured-output design means the model returns *data*, not free-form
instructions it could be tricked into "executing".

**Q: How do you track cost per request across a multi-agent pipeline?**
A: A context-var usage accumulator; the LLM client records each call's tokens
into it, and the `@traced` decorator attributes a token/cost delta to each node.
The total is logged per analysis and returned in the SSE stream. Cost is computed
from a per-model price table.

**Q: Why a deterministic citation metric when you already have LLM judges?**
A: The anti-hallucination guarantee shouldn't depend on another LLM's opinion.
Citation existence + text overlap is checkable against the corpus directly, so we
hold it to the highest threshold and it runs with no key.

**Q: You use Gemini to judge Gemini's output — isn't that circular?**
A: For the LLM-judged metrics it's a known limitation (mitigated by using the
stronger Pro model as judge and pairing with deterministic checks + a curated
gold standard). The deterministic Citation Accuracy and the expected-section
comparison don't rely on the judge at all.

**Q: Why is the eval suite separate from the default tests?**
A: It needs the heavy `eval` group and a real LLM (cost + latency + a key). CI's
default run stays fast and offline; the eval suite runs as its own gated job.
