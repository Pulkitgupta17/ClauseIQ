# ClauseIQ — Architecture

> Interview-prep doc. Explains **what** each layer is, **why** it's there, and
> **how** the pieces talk to each other. Read this first; component docs under
> `docs/components/` go deeper on each piece.

## 1. What ClauseIQ is (one paragraph)

ClauseIQ reads an Indian contract, flags clauses that are unfair to the weaker
party (tenant, junior employee, freelancer, small business), scores each flag by
severity, and backs every flag with a citation to the exact section of Indian
law (e.g. *Section 23, Indian Contract Act, 1872*). It runs two ways: as a
**web app** (FastAPI + React, with Gemini doing the reasoning) and as an **MCP
server** inside Claude Desktop (Claude is the reasoning "supervisor", and free
Gemini still does internal sub-tasks).

## 2. The architecture in one sentence

**Clean / hexagonal architecture** with a strict dependency rule: code is split
into four concentric layers and **dependencies only ever point inward**.

```
            ┌─────────────────────────────────────────────┐
            │  interfaces/   (FastAPI routes, MCP server)  │   ← outermost
            │   ┌─────────────────────────────────────┐   │
            │   │  infrastructure/  (Chroma, BM25,     │   │
            │   │   embedder, PDF, LLM, repositories)  │   │
            │   │   ┌─────────────────────────────┐    │   │
            │   │   │  application/  (use cases,   │    │   │
            │   │   │   LangGraph agents)          │    │   │
            │   │   │   ┌─────────────────────┐    │    │   │
            │   │   │   │  domain/  (pure)    │    │    │   │   ← innermost
            │   │   │   │  entities, Result,  │    │    │   │
            │   │   │   │  enums, ports       │    │    │   │
            │   │   │   └─────────────────────┘    │    │   │
            │   │   └─────────────────────────────┘    │   │
            │   └─────────────────────────────────────┘   │
            └─────────────────────────────────────────────┘
        Arrows of dependency point INWARD only. The domain knows
        nothing about Chroma, FastAPI, Gemini, or MCP.
```

### The four layers

| Layer | Folder | Knows about | Contains |
|-------|--------|-------------|----------|
| **Domain** | `src/clauseiq/domain/` | nothing (pure Python stdlib) | entities, value objects, `Result`, exceptions, **ports** (interfaces) |
| **Application** | `src/clauseiq/application/` | domain only | use cases (`analyze_contract`), LangGraph agents, Pydantic I/O schemas |
| **Infrastructure** | `src/clauseiq/infrastructure/` | domain + application | adapters: ChromaDB, BM25, embedder, PDF parser, chunker, Gemini, repositories, guardrails |
| **Interfaces** | `src/clauseiq/interfaces/` | all of the above | FastAPI app + routes, MCP server + tools |

## 3. The dependency rule (the thing interviewers probe)

> **Inner layers must not import outer layers.**

The domain defines **ports** (Python `Protocol`s like `Retriever`, `VectorStore`,
`Embedder`, `LawRepository`). The application orchestrates against those ports.
The infrastructure provides concrete **adapters** that satisfy them. Wiring
(which concrete adapter is used) happens at the edge, via **dependency
injection** in `interfaces/api/dependencies.py` / the MCP server.

**Why this matters:**
- The business logic is testable with zero I/O — we mock a port, not a database.
- We can swap ChromaDB for another store, or Gemini for Claude, without touching
  domain or application code. (This is the Dependency Inversion Principle.)
- It's also what makes the same core usable from **both** FastAPI and MCP: those
  are just two different "interfaces" wrapping the same use cases.

## 4. How a request flows (web mode, target end state)

```
PDF upload (React, react-dropzone)
   │  HTTP POST /analyze  (multipart)
   ▼
FastAPI route ──► application use case: analyze_contract()
   │                         │
   │                         ▼
   │                LangGraph SUPERVISOR  (Gemini 2.0 Flash routes)
   │                 ├──► Retriever worker      → hybrid search (BM25 + dense, RRF)
   │                 ├──► Risk Analyzer worker   → Gemini 2.5 Pro scores clauses
   │                 └──► Citation Verifier      → checks each citation is real
   │                         │
   ▼                         ▼
SSE stream  ◄──────  step-by-step events (trace_id on every event)
(React EventSource shows "Retrieving law…" → "Analyzing…" → "Verifying…")
```

In **MCP mode**, Claude Desktop *is* the supervisor: it calls our MCP tools
(retrieve law, analyze clause, verify citation), each of which is the same
application use case. Internal sub-tasks still use free Gemini Flash.

## 5. Cross-cutting concerns

- **Configuration** — `config.py`, one `Settings` object from env vars
  (`CLAUSEIQ_*`), 12-factor. See `docs/components/config-and-logging.md`.
- **Logging** — `structlog`, structured JSON, every line carries a `trace_id`
  so one analysis can be followed across the supervisor and all workers.
- **Error handling** — two channels: a `Result[T, E]` type for *expected*
  failures (no search hits, low confidence) and a custom exception hierarchy
  (`ClauseIQError`) for bugs/invariant violations. No bare `except`.

## 6. Key design patterns used (and where)

| Pattern | Where | Why |
|---------|-------|-----|
| **Ports & Adapters (Hexagonal)** | `domain/ports.py` + `infrastructure/` | swap implementations, test without I/O |
| **Repository** | `infrastructure/repositories/` | hide vector-store details behind a domain-friendly API |
| **Strategy** | `retrieval/{bm25,dense,hybrid}.py` | interchangeable retrieval algorithms behind one `Retriever` port |
| **Factory** | `infrastructure/llm/factory.py` | pick an LLM client by name/role |
| **Result type** | `domain/result.py` | make expected failures explicit in the type system |
| **Dependency Injection** | `interfaces/.../dependencies.py` | wire adapters at the edge, keep inner layers pure |
| **Supervisor / multi-agent** | `application/agents/` | LangGraph state machine delegating to workers |

## 7. The data pipeline (Milestone 1 — built first)

```
data/laws/indian_contract_act_1872.json   (committed source of truth, versioned)
   │  scripts/ingest_laws.py
   ▼
PDF parser / JSON loader ──► Chunker (clause-aware, 250-token windows)
   │                              │
   │                              ▼
   │                       Embedder (all-MiniLM-L6-v2, 384-dim, local)
   ▼                              │
ChromaDB (dense vectors)  ◄───────┘     +  BM25 sparse index (rank-bm25)
                       │                          │
                       └──────────► Hybrid Retriever (RRF fusion) ──► ScoredChunk[]
```

The corpus is **committed JSON** (deterministic, testable) rather than scraped
live each run; freshness fields (`effective_date`, `last_amended`,
`source_fetched_at`, `corpus_version`) flow into every `Citation`. See
`docs/components/chunking.md` and the retrieval component docs.

## 8. Tech stack (and the one-line "why" for each)

See the README's stack table. The load-bearing choices: **LangGraph** (explicit
state-machine control flow + observability), **ChromaDB + BM25** (free hybrid
retrieval — dense catches meaning, sparse catches exact legal terms), **Gemini
free tier** (zero LLM cost in web mode), **MCP** (runs inside Claude Desktop on
the user's own Pro plan), **all-MiniLM-L6-v2** (free, local, fast embeddings).
