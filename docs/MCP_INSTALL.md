# Installing the ClauseIQ MCP server in Claude Desktop

ClauseIQ exposes three tools to Claude Desktop over MCP (stdio):

| Tool | What it does |
|------|--------------|
| `analyze_contract(contract_text)` | Full multi-agent analysis → risk flags with severity + cited law |
| `search_indian_law(query, k=5)` | Hybrid search over the Indian Contract Act, 1872 |
| `verify_citation(claim, citation)` | Confirms a cited section actually exists in the corpus |

## 1. Prerequisites (one-time)

From the project root:

```bash
uv sync                                   # install dependencies
uv run python scripts/ingest_laws.py      # build the local law corpus in ChromaDB
```

- `search_indian_law` and `verify_citation` work with **no API key** (local
  embeddings + corpus).
- `analyze_contract` needs a free Google AI Studio key. Put it in `.env` at the
  project root (it is gitignored):

  ```bash
  echo 'CLAUSEIQ_GEMINI_API_KEY=your-aistudio-key' >> .env
  ```

> Heads-up: if model downloads hang, the sandbox/network may block HuggingFace's
> Xet CDN — set `HF_HUB_DISABLE_XET=1` (see the env block below).

## 2. Add the server to Claude Desktop

Edit `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add (replace the path with your **absolute** project path):

```json
{
  "mcpServers": {
    "clauseiq": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/ABSOLUTE/PATH/TO/ClauseIQ",
        "clauseiq-mcp"
      ],
      "env": {
        "HF_HUB_DISABLE_XET": "1"
      }
    }
  }
}
```

The key in `.env` is picked up automatically because `uv run --directory` sets
the working directory to the project. (Alternatively, put
`"CLAUSEIQ_GEMINI_API_KEY": "your-key"` in the `env` block instead of `.env`.)

If `uv` is not on Claude Desktop's `PATH`, use its absolute path (`which uv`) or
point `command` at the venv directly:

```json
{ "command": "/ABSOLUTE/PATH/TO/ClauseIQ/.venv/bin/clauseiq-mcp", "args": [] }
```

## 3. Restart Claude Desktop and test

Fully quit and reopen Claude Desktop. You should see a tools/plug icon for
`clauseiq`. Try a demo prompt:

> "Use ClauseIQ to search Indian law for *agreement in restraint of trade*."

or

> "Analyze this contract with ClauseIQ: *<paste a short rental/employment clause set>*"

or

> "Verify with ClauseIQ that *Section 27* exists and supports the claim that a
> non-compete after employment is void."

Claude (the supervisor in MCP mode) will call the tool, and you'll see the
structured result.

## Troubleshooting

- **Tool not listed / server fails to start:** check the path is absolute and
  `uv` is reachable; run `uv run clauseiq-mcp` manually in the project — it
  should start and wait on stdin (Ctrl-C to exit).
- **`analyze_contract` returns `analysis_failed: ... api_key_missing`:** the
  Gemini key isn't set; add it to `.env` or the `env` block.
- **Empty law results:** run `scripts/ingest_laws.py` first (the corpus must be
  ingested into ChromaDB).
- **Logs:** ClauseIQ logs to **stderr** (stdout is reserved for the MCP
  protocol); Claude Desktop's MCP logs capture them.
