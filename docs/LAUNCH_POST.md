# LinkedIn Launch Post (draft)

~300 words. Tune the personal hook before posting.

---

I built **ClauseIQ** — an AI system that reads an Indian contract, flags the
clauses that are unfair to *you*, and cites the exact section of law behind each one.

The idea came from watching friends sign rental and employment contracts with
clauses that are quietly unenforceable under Indian law — 12-month lock-ins that
forfeit your entire deposit, two-year non-competes, "raise any dispute within 7
days or lose it forever." Most people have no way to know.

So I built the thing I wished existed — and treated it like a production system,
not a demo.

Under the hood it's a **multi-agent pipeline** (LangGraph): a supervisor segments
the contract, a retriever pulls relevant law via **hybrid search** (vector +
BM25), a risk analyzer scores each clause 1–5, and a citation verifier checks
every cited section actually exists — so the citations are grounded, not
hallucinated.

A few things I'm proud of:
• **One core, two front doors.** The same engine runs as a streaming web API
  *and* as an **MCP server** — so I can analyse contracts directly inside Claude
  Desktop.
• **Eval-gated CI.** Releases fail automatically if faithfulness or citation
  accuracy regress, measured against a 20-case golden dataset.
• **Cost-aware.** Built on Gemini's free tier with per-query cost tracking and
  full tracing in Langfuse.

Stack: Python, FastAPI, LangGraph, ChromaDB, Gemini, MCP, DeepEval on the
backend; React, Vite, Tailwind, and a live streaming UI on the front.

It's open source and deployed:
🔗 Live app: clauseiq.vercel.app
🔗 Code: github.com/Pulkitgupta17/ClauseIQ

Disclaimer: it's decision-support, not legal advice.

If you're building with multi-agent systems or RAG, I'd love feedback — especially
on the evaluation harness, which was the hardest and most interesting part.

#AI #LLM #LangGraph #RAG #MCP #SoftwareEngineering #LegalTech
