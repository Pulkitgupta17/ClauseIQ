# Component: Law Repository & Health API

**Files:** `src/clauseiq/infrastructure/repositories/law.py`,
`src/clauseiq/interfaces/api/main.py`
**Tests:** `tests/unit/test_law_repository.py`, `tests/unit/test_health.py`

## Law repository (`ChromaLawRepository`)

A **repository** is a domain-friendly facade over storage. It implements the
domain `LawRepository` port and hides ChromaDB + the retrieval strategies behind
three operations, returning domain types (`ScoredChunk`, `Citation`) and
`Result` values:

- `search(query, k)` — delegates to the hybrid retriever; wraps any retrieval
  error as a `RepositoryError` (`Result`).
- `get_section(law_code, number)` — looks up a section by its stable id
  (`ICA_1872:s23`) via a metadata filter and rebuilds a `Citation` from the
  stored metadata; returns `LawSectionNotFoundError` if absent.
- `count()` — number of **distinct sections** (de-duplicates chunk → section).

`to_citation()` reconstructs a `Citation` from chunk metadata (law code, number,
title, full section text, source URL, freshness dates) and **clamps** the
relevance score into [0, 1].

### The amendment guardrail (in code, not just docs)

`amendment_history_note(citation)` returns *"Amendment history not tracked —
verify current law…"* whenever `last_amended` is unknown. The frontend shows
this so a citation never *implies* it reflects the current, amended law — the
honesty requirement from the corpus decision, enforced where citations are built.

## Health API (`interfaces/api/main.py`)

`app` is the **canonical** FastAPI instance (later milestones attach
`/api/v1/*` and SSE routes to *this* app, not a parallel one). Two endpoints:

- **`GET /health`** — *liveness*. Always 200 if the process is up. Used by the
  Docker/compose health check and orchestrators to know the container is alive.
- **`GET /health/ready`** — *readiness*. Pings ChromaDB (`store.count()`) with a
  **2-second timeout**; returns 200 `{"status":"ready","indexed_chunks":N}` when
  the dependency answers, else **503** `{"status":"degraded"}`. This is what
  decides whether traffic should be routed to the instance.

Why split liveness vs readiness? A live-but-not-ready instance (e.g. ChromaDB
still starting) should not receive traffic but should *not* be killed — only
readiness flips to 503, so the orchestrator waits instead of restart-looping.

The shared store is created once in the FastAPI **lifespan** and kept on
`app.state`, so the readiness probe reuses one client.

## Likely interview questions

**Q: What's the point of the repository layer over just calling Chroma?**
A: It keeps infrastructure details out of the application/agents. They depend on
the `LawRepository` port and get domain `Citation`/`Result` objects; we can swap
ChromaDB or the retrieval mix without touching business logic, and we test
against a fake repository.

**Q: Liveness vs readiness — why both?**
A: Liveness answers "is the process alive?" (restart if not). Readiness answers
"can it serve traffic *right now*?" (route around it if not). Conflating them
makes orchestrators kill instances that are merely warming up.

**Q: Why is readiness time-boxed?**
A: A health probe must fail fast. If ChromaDB hangs, `asyncio.wait_for` returns a
503 within 2s instead of letting the probe block, so load balancers react
quickly.
