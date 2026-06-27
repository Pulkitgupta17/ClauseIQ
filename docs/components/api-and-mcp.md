# Component: HTTP API & MCP Server (the two interfaces)

**Files:** `src/clauseiq/interfaces/api/{main,routes,dependencies}.py`,
`src/clauseiq/interfaces/mcp/{server,tools}.py`
**Tests:** `tests/integration/test_api.py`, `tests/integration/test_mcp_server.py`

## One core, two interfaces

The same `analyze_contract` use case is exposed two ways. This is the payoff of
the hexagonal design — the interfaces are thin adapters; all the logic lives in
the application/domain layers.

```
                 ┌─────────────── application use cases ───────────────┐
HTTP (React) ───►│  ContractAnalyzer.analyze / .stream                 │◄─── MCP (Claude Desktop)
                 │  LawRepository.search / .get_section                │
                 └─────────────────────────────────────────────────────┘
```

## HTTP API (`interfaces/api/`)

### Routes (`routes.py`)
- `POST /api/v1/analyze` → full `ContractAnalysis` (502/503 on LLM failure).
- `POST /api/v1/analyze/stream` → **SSE**, one event per agent (live progress).
- `GET /api/v1/law/{section_id}` → citation drill-down (`ICA_1872:27` or `27`).
- `GET /healthz` (+ `/health`, `/health/ready` from M1).

SSE is written by hand (`StreamingResponse` + `text/event-stream`,
`event: <name>\ndata: <json>\n\n`) to avoid an extra dependency.

### Dependency injection (`dependencies.py`)
The analyzer and law repository are **heavy** (they load the embedding model and
build the BM25 index), so they're built **once, lazily, cached on `app.state`**
behind a lock. Tests swap them out via `app.dependency_overrides`, so route
tests never load a model or call an LLM.

### Middleware & errors (`main.py`)
- A middleware stamps each request with a `trace_id` (→ logs + `X-Trace-Id`
  header) and logs method/path/status/latency.
- Exception handlers turn `ClauseIQError` into clean JSON (right status code) and
  guarantee an unexpected error returns only `{"error":"internal_error",
  "trace_id":...}` — **no internal details leak**.
- `app` is the canonical instance the M1 health endpoints already used.

## MCP server (`interfaces/mcp/`)

`FastMCP` server over **stdio** exposing three tools:
`analyze_contract`, `search_indian_law`, `verify_citation`. In MCP mode **Claude
Desktop is the supervisor** — it decides which tool to call; internal sub-tasks
still run on free Gemini.

- Heavy resources are built lazily and cached in a shared `ToolContext`.
- Tools return plain JSON dicts and **never raise across the boundary** — failures
  come back as `{"error": ...}` so Claude can react.
- **Logs go to stderr** (configured globally) because stdout is the MCP JSON-RPC
  channel — a classic stdio-MCP footgun handled once, centrally.

Install steps + the exact `claude_desktop_config.json` are in
[`docs/MCP_INSTALL.md`](../MCP_INSTALL.md).

## Likely interview questions

**Q: Why expose the same logic over both HTTP and MCP?**
A: Reach and cost. The web app (Gemini) serves anyone; the MCP server lets a
Claude Desktop Pro user drive the tools at zero cost to us. Because the core is
behind ports, both interfaces are ~100-line adapters over the *same* use cases.

**Q: Liveness vs readiness vs healthz — why several?**
A: `/health`/`/healthz` are liveness (process up). `/health/ready` is readiness
(can it serve — it pings ChromaDB with a 2s timeout, 503 if degraded). Splitting
them lets orchestrators wait on a warming instance instead of killing it.

**Q: How is streaming implemented and why SSE (not WebSocket)?**
A: SSE is one-way server→client, which is exactly the agent-progress use case,
and it works with the browser's native `EventSource`. The endpoint iterates the
analyzer's event stream and writes `text/event-stream` frames.

**Q: Why build the analyzer lazily behind a lock?**
A: It loads a model and builds an index — expensive. Building it on first request
(once, guarded by a lock) keeps startup fast and avoids double-loading under
concurrent first requests; tests override it entirely.

**Q: How do you keep secrets and internals out of responses/logs?**
A: The API key is a `SecretStr`; the catch-all exception handler returns only an
error code + `trace_id`; logs are structured and go to stderr. You correlate via
the `trace_id`, never by leaking stack traces.
