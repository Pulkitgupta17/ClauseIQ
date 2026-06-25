# ClauseIQ

**A multi-agent AI system that reads an Indian contract, flags clauses that are
unfair to the weaker party with a severity score, and backs every flag with a
citation to the exact section of Indian law.** It runs as a web app and as an
MCP server inside Claude Desktop.

> This is a **case-study README** — it explains the *what* and *why*. Build/run
> details live in `docs/` and the scripts; architecture in `docs/ARCHITECTURE.md`.

## The problem

Tenants, junior employees, freelancers, and small businesses sign contracts they
can't fully evaluate. A lock-in that's unenforceable, a one-sided indemnity, an
auto-renewal trap — these hide in dense legalese. ClauseIQ surfaces them in plain
language and, crucially, **cites the law** (Indian Contract Act 1872, Specific
Relief Act, Consumer Protection Act, state rent-control acts) so the output is
checkable, not a black box.

## What makes it interesting (the engineering story)

- **Clean / hexagonal architecture** with a strict dependency rule — a pure
  domain core, swappable adapters, the *same* use cases exposed over both FastAPI
  and MCP. See `docs/ARCHITECTURE.md`.
- **Multi-agent supervisor** (LangGraph): a supervisor delegates to Retriever,
  Risk Analyzer, and Citation Verifier workers. In MCP mode, Claude Desktop *is*
  the supervisor; internal sub-tasks use free Gemini.
- **Hybrid retrieval** (dense embeddings + BM25, fused with Reciprocal Rank
  Fusion) over a corpus of real statutory text, so retrieval catches both
  meaning and exact legal terms.
- **Zero LLM cost** in web mode (Gemini free tier) and zero embedding cost
  (local `all-MiniLM-L6-v2`).
- **Production discipline:** Pydantic v2 at every boundary, `mypy --strict`,
  structured logging with a `trace_id`, a `Result` type for expected failures,
  property-based tests, and a reproducible, versioned law corpus.

## Tech stack (one-line *why* each)

| Area | Choice | Why |
|------|--------|-----|
| Lang / pkg | Python 3.11, `uv` | async-first; fast, modern lockfile |
| API | FastAPI | async, OpenAPI, Pydantic-native |
| Agents | LangGraph | explicit state-machine control flow |
| LLMs (web) | Gemini 2.0 Flash + 2.5 Pro | strong, free tier, no API cost |
| LLM (MCP) | Claude (user's Desktop Pro) | supervisor at zero cost to us |
| Embeddings | sentence-transformers MiniLM | free, local, 384-dim |
| Vector DB | ChromaDB | free, embeddable, metadata filters |
| Lexical | rank-bm25 | exact-term half of hybrid retrieval |
| Validation / logs | Pydantic v2 / structlog | typed I/O / structured `trace_id` logs |
| Eval / obs | DeepEval / Langfuse | LLM-as-judge / tracing + cost |
| Infra | Docker, GitHub Actions, Render/Vercel | standard, free tiers |

## Status

**Milestone 1 (Foundation) — complete.** End-to-end data pipeline: project
scaffolding, the pure domain layer, the clause-aware chunker, hybrid retrieval
(BM25 + dense + RRF) over ChromaDB, a versioned Indian Contract Act corpus
(266 sections parsed from the official PDF), the law repository, a health API,
and `docker-compose` for the full local stack. All gates green (`ruff`,
`mypy --strict`, ~100 tests, 100% domain coverage).

Later milestones: the LangGraph agents, the analysis use case, guardrails, the
MCP server, the eval harness, and the React frontend.

## A note on legal accuracy

The law corpus is the official consolidated Act text, fetched from
[indiacode.nic.in](https://www.indiacode.nic.in/), committed and **versioned**.
Per-section **amendment history is not tracked** — `last_amended` is honestly
`null` where it can't be derived, and the UI shows an "amendment history not
tracked" note. ClauseIQ is decision-support, **not legal advice**; users should
verify current law for time-sensitive matters.

## What I'd do differently / next

- **Automated weekly corpus refresh** *(stretch — architecture already supports
  it).* A scheduled GitHub Action runs `fetch_ica_source.py` + `diff_law_corpus.py`
  weekly, posts the human-readable diff to Slack, and opens a PR that requires
  **human approval** before the refreshed corpus is merged. The pieces exist
  (deterministic fetch, normalized diff, versioned JSON); only the workflow and
  notification wiring remain. This keeps the law current without ever
  auto-merging legal-text changes unreviewed.
- **An amendments database** so `last_amended` becomes real per-section data
  (the schema already carries `is_amendment_history_known` to flip on later).
- **More statutes** beyond the Contract Act (Specific Relief, Consumer
  Protection, state rent-control acts) using the same ingestion pipeline.
- **A longer-context embedder** to allow larger chunks (the current 250-token
  size is bounded by MiniLM's 256-token window).
