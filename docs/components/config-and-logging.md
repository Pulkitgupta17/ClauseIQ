# Component: Configuration & Logging

**Files:** `src/clauseiq/config.py`, `src/clauseiq/logging_config.py`
**Env template:** `.env.example`

## Configuration (`config.py`)

One `Settings` class (`pydantic-settings`) reads everything from environment
variables prefixed `CLAUSEIQ_` (optionally seeded by a local `.env`). One
validated `settings` object is created once and shared by importers.

### What it holds
LLM keys + model names, embedding model, ChromaDB host/port/collection/persist
dir, chunking params (`chunk_max_tokens=250`, `chunk_overlap_tokens=25`), law
corpus path + `corpus_version`, Langfuse keys/host, eval thresholds, and
runtime/logging (`log_level`, `log_json`, `environment`).

### Three design decisions worth explaining

1. **Secrets are optional with empty defaults.** 12-factor says config must load
   even when a capability's credentials are absent. The whole data pipeline
   (ingestion + retrieval) runs with **no** LLM/Langfuse keys. The LLM factory
   validates the key *at point of use* and returns a typed failure — we don't
   crash the process at import just because one feature isn't configured.

2. **Validation at the boundary.** Ports/ranges are enforced by Pydantic
   (`chroma_port` 1–65535, thresholds 0–1) and a `model_validator` ensures
   `chunk_overlap_tokens < chunk_max_tokens`. Bad config fails fast and loud.

3. **`corpus_version` is derived.** If not set in the env, it's read from the
   law-corpus JSON's top-level `version` field (falling back to `"unversioned"`
   if the file is missing — which it is before ingestion runs). This value flows
   into every `Citation` so the UI can show "Law corpus current as of …".

## Logging (`logging_config.py`)

`structlog` configured once at startup. Every log call is a **structured event**
(key/value pairs), rendered as **JSON in production** and pretty colours in dev.

### The `trace_id` story (the important part)
A `trace_id_var` `ContextVar` holds the current trace id. A structlog processor
stamps it onto **every** log line automatically. `ContextVar` propagates across
`async`/`await` and `asyncio` tasks, so a single contract analysis — supervisor
plus every worker agent — shares one trace id without us threading it through
every function call.

```python
with trace_context() as trace_id:      # generates or adopts an id
    log.info("analyzing_clause", clause_id="cl1")   # trace_id auto-attached
```

`print()` is never used anywhere in `src/` — this is the rule that makes logs
machine-parseable and greppable by `trace_id` in Langfuse/any log tool.

## Likely interview questions

**Q: Why structured (JSON) logging?**
A: Logs become queryable data, not prose. In production you filter by
`trace_id`, `agent_name`, `clause_id`, latency, cost — impossible to do reliably
with free-text `print`s.

**Q: How does one `trace_id` follow an async, multi-agent request?**
A: It's stored in a `ContextVar`, which Python propagates across `await` points
and tasks. A structlog processor reads it on every emit, so all logs from the
supervisor and workers in that request carry the same id — that's how you
reconstruct the full trace.

**Q: Why are API keys allowed to be empty by default?**
A: 12-factor + graceful degradation. Config must load without every secret so
non-LLM features (the data pipeline, tests, CI) run keyless. Presence is checked
where the key is actually used, and surfaced as a typed `Result`/error.

**Q: Where do the chunk size / thresholds live and why config?**
A: In `Settings`, not hardcoded — they're behaviour knobs (e.g. chunk size is
tied to the embedder's context window). Centralising them makes the system
12-factor and lets us tune per environment without code changes.
