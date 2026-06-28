# Component: Multi-Agent Analysis Pipeline

**Files:** `src/clauseiq/application/agents/*.py`, `application/workflows.py`,
`application/schemas.py`, `infrastructure/llm/*.py`
**Tests:** `tests/integration/test_workflow.py`, `tests/unit/test_llm.py`,
`tests/unit/test_schemas.py`

## The pipeline in one picture

```
contract_text
   │
   ▼
SUPERVISOR (Gemini Flash) ──► is it a contract? → segment into clauses
   │                            + propose retrieval queries  (SegmentationResult)
   │  (not a contract → END)
   ▼
RETRIEVER (no LLM) ──► hybrid-search each query → de-duped, ranked law pool
   │
   ▼
RISK ANALYZER (Gemini Pro) ──► per-clause context (clause + most-relevant law)
   │                            → one structured call → flags (severity 1-5)
   ▼
CITATION VERIFIER (no LLM) ──► check every proposed citation against the corpus;
   │                            drop unverifiable ones → domain RiskFlags
   ▼
ContractAnalysis  (+ SSE event after each node)
```

Built as a **LangGraph `StateGraph`** (`build_analysis_graph`). Each agent is a
node that reads the shared `AnalysisState` and returns a partial update.

## Why a multi-agent / supervisor design?

Splitting the job into specialised agents makes each step **independently
testable, observable, and replaceable**, and lets us use the *cheap* model where
speed matters (Flash: triage + segmentation) and the *strong* model where
reasoning matters (Pro: risk judgement). In **MCP mode**, Claude Desktop is the
outer supervisor — it decides which tool to call — while this same pipeline runs
inside `analyze_contract`.

## The four agents

1. **Supervisor (Flash).** Input guardrail (`is_contract`), clause segmentation,
   and retrieval-query planning — returned as a **validated `SegmentationResult`**,
   not parsed text. If it's not a contract, the graph routes straight to END.
2. **Retriever (no LLM).** Runs each query through the hybrid `LawRepository`,
   merges hits into one de-duplicated, score-ranked law pool.
3. **Risk Analyzer (Pro).** For each clause it builds context **deterministically**
   — the clause plus the pool chunks most lexically relevant to it — and sends the
   assembled clauses+law to Pro in **one** structured call. It deliberately does
   **not** see the raw contract (only the segmented clauses), avoiding
   re-segmentation drift/contamination. Severity is a strict 1-5; an out-of-range
   value fails Pydantic validation and the call is retried.
4. **Citation Verifier (no LLM).** The anti-hallucination gate: every proposed
   `(law_code, section)` is looked up in the corpus; only ones that **exist**
   survive. It then assembles validated domain `RiskFlag`s (1-5 → `Severity`
   enum, clause-type → `ClauseType`).

## Structured output (no prose parsing)

Agents call `LLMClient.generate_structured(prompt, Schema)`, which uses Gemini's
`response_schema` to force JSON matching a Pydantic model (`SegmentationResult`,
`RiskAnalysisResult`). The result is validated data — if the model returns
malformed JSON or an out-of-range score, it's an `Err`, and the analyzer retries.
This is what makes LLM output safe to put straight into the domain.

## Severity: 1-5 ↔ the enum

The analyzer emits an integer **1-5** (calibrated by definitions in the system
prompt). `Severity.from_score()` maps it `1→INFO … 5→CRITICAL`; the API exposes
**both** the raw `severity_score` and the `severity_label`. The domain enum never
changed — the 1-5 scale is a boundary concern.

## The LLM layer (`infrastructure/llm/`)

- `LLMClient` port → `GeminiClient` (text + structured), thin `GeminiFlashClient`
  / `GeminiProClient`, and a role `factory`.
- Failures are `Result`/`Err(LLMError)`, never exceptions; HTTP 429/5xx are
  retried with exponential backoff.
- The key is a **`SecretStr`** so it never appears in logs or tracebacks.
- Tests fake the SDK — no key, fully offline.

## Streaming (SSE)

`ContractAnalyzer.stream()` runs the graph with LangGraph's `astream(...,
"updates")` and yields a `StreamEvent` as each node finishes:
`supervisor_start → supervisor_complete → retriever_complete →
risk_analyzer_complete → citation_verifier_complete → done`. `analyze()` is the
non-streaming twin (`ainvoke`). Both share `_build_analysis`.

## Likely interview questions

**Q: Why use two different Gemini models?**
A: Cost/latency vs quality. Flash is fast and cheap for high-frequency
orchestration (triage, segmentation); Pro does the one hard reasoning call. Both
are free-tier, so there's no API cost.

**Q: How do you stop the LLM hallucinating fake citations?**
A: The analyzer only *proposes* citations; the Citation Verifier checks each one
against the real corpus via `get_section` and drops any that don't exist. A
flag's legal backing is always a section that actually exists.

**Q: Why force structured output instead of parsing text?**
A: Reliability. `response_schema` + Pydantic means the agent returns typed,
validated data; a bad/out-of-range value is caught and retried instead of
silently flowing downstream.

**Q: Why doesn't the analyzer see the raw contract?**
A: To avoid contamination/re-segmentation. The supervisor already segmented the
clauses; the analyzer reasons over those exact clauses + their retrieved law, so
clause boundaries and indices stay stable.

**Q: How does the SSE order stay deterministic?**
A: The graph edges are fixed (supervisor→retriever→analyzer→verifier), and we
emit one event per node as `astream` reports its completion — so the event order
mirrors the graph order every time.
