# ClauseIQ — 3-Minute Demo Shot List

Target length **3:00**. Record at 1080p, dark mode, large font. Keep cuts tight;
narration in **bold**, on-screen action in plain text.

---

## 0:00–0:20 — The problem
**"Most people sign rental, employment, and freelance contracts in India without
knowing which clauses are unfair — or illegal. A lock-in that forfeits your whole
deposit. A two-year non-compete. These are often unenforceable under Indian law,
but you'd never know."**

- Open on a real-looking one-sided rental PDF, scroll past the scary clauses.
- Title card: **ClauseIQ — know what you're signing.**

## 0:20–0:50 — Architecture
**"ClauseIQ is a multi-agent system. A supervisor segments the contract, a
retriever pulls the relevant sections of Indian law with hybrid search, a risk
analyzer scores each clause 1–5, and a citation verifier checks every cited
section actually exists — so nothing is hallucinated."**

- Show the architecture diagram (README) — highlight the 4 agents left-to-right.
- Call out: **one core, two front doors — a REST/streaming API and an MCP server.**

## 0:50–1:40 — Live demo in Claude Desktop (MCP)
**"Because it's an MCP server, I can use it right inside Claude Desktop."**

- In Claude Desktop, type: *"Analyse this rental agreement for unfair clauses"* and paste the sample.
- Show Claude calling the `analyze_contract` tool; results stream back with severity + cited sections.
- Click one citation point: **"§74 — penalty clauses are capped at reasonable compensation."**

## 1:40–2:20 — The React app (streaming UI)
**"The same engine powers a web app — with the agents streaming live."**

- Open the Vercel URL. Paste the same contract (or "Try sample contract"), hit Analyse.
- Show the **AgentTrace** lighting up step by step, then clause cards animating in with the risk gauge.
- Expand a card; open a citation dialog showing the full statutory text.

## 2:20–2:40 — Trust: evals + traces
**"This isn't a vibe check. Every release is gated on an eval suite, and every
run is traced."**

- Show the **Evaluation Results** table (Faithfulness, Citation Accuracy, etc.).
- Show a **Langfuse** trace: the 4 agent spans, latency, tokens, cost-per-query.

## 2:40–3:00 — Links & close
**"It's open source, deployed, and installable into Claude Desktop in under a
minute. Links below."**

- On-screen: **GitHub** (github.com/Pulkitgupta17/ClauseIQ), **Live app** (clauseiq.vercel.app), **API health** (clauseiq-api.onrender.com/healthz).
- End card: **ClauseIQ — built with LangGraph, Gemini, and a lot of Indian contract law.**

---

### Recording checklist
- [ ] Claude Desktop has the MCP server installed and a fresh chat open.
- [ ] Backend + frontend both warm (hit them once before recording to avoid cold starts).
- [ ] `.env` has a credited Gemini key; spend cap is comfortable.
- [ ] Langfuse dashboard pre-loaded to the right project.
- [ ] Sample contract copied to clipboard.
