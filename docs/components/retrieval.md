# Component: Embeddings, Vector Store & Hybrid Retrieval

**Files:** `src/clauseiq/infrastructure/vectorstore/{embedder,chroma}.py`,
`.../retrieval/{base,dense,bm25,hybrid}.py`
**Tests:** `tests/unit/test_embedder.py`, `test_retrieval_strategies.py`,
`tests/integration/test_chroma.py`

## The retrieval stack at a glance

```
query ─┬─► DenseRetriever  ─► embed(query) ─► ChromaDB nearest (cosine)  ─┐
       │                                                                   ├─► RRF fusion ─► top-k
       └─► BM25Retriever   ─► rank-bm25 over the same chunks  ────────────┘
```

## Why hybrid (dense + sparse)?

Two retrieval styles fail in opposite ways, so we run both:

- **Dense** (embeddings, semantic): catches *meaning* — "you can't quit for a
  year" matches a lock-in clause even with no shared words. Weak on rare exact
  tokens.
- **BM25** (lexical, sparse): catches *exact terms* — "Section 27", "indemnify",
  "lock-in". Weak on paraphrases.

Hybrid retrieval gets the recall of both.

## Embedder (`embedder.py`)

`SentenceTransformerEmbedder` implements the domain `Embedder` port using
`all-MiniLM-L6-v2` (384-dim, local, free). Notes:

- **Lazy model load**, reused across calls.
- Synchronous library → every encode runs in a worker thread
  (`asyncio.to_thread`) so the event loop stays responsive (async-first).
- Embeddings are **L2-normalised**, so dot product = cosine similarity (matches
  ChromaDB's cosine space).
- Failures are wrapped as a domain `EmbeddingError` at the boundary.

## Vector store (`chroma.py`) — storage only

`ChromaVectorStore` implements the `VectorStore` port. By design it **does not
embed** — it stores precomputed vectors (embedding is a separate, swappable
concern; Single Responsibility). The Chroma client is **injected** (DI), so tests
use an in-memory `EphemeralClient` and prod uses a persistent or HTTP client
(`chroma_mode`). Cosine *distances* from Chroma are converted to a *similarity
score* (`1 − distance`) so higher always means more relevant.

## Retrieval strategies (Strategy pattern)

All implement `BaseRetriever` and the domain `Retriever` port, so they're
interchangeable. Shared error/empty contract: **infra failure → `Err`**,
**ran-but-empty → `Ok([])`** (lets the fuser combine partial results).

### Reciprocal Rank Fusion (the key idea)

We **don't** add raw scores — BM25 scores and cosine similarities live on
different, incomparable scales. RRF uses only each result's **rank**:

```
score(d) = Σ_retrievers  1 / (rrf_k + rank_r(d))        # rrf_k = 60 (paper default)
```

A document ranked highly by *both* retrievers floats to the top; no score
normalisation needed. If one retriever errors, the other still produces results;
only if *all* fail does hybrid return `Err`.

## Likely interview questions

**Q: Why RRF instead of weighting/combining the scores?**
A: BM25 and cosine scores aren't on the same scale, so summing them is
meaningless without calibration. RRF only needs ranks, so it fuses heterogeneous
retrievers robustly with one tunable constant (`rrf_k`).

**Q: Why does the Chroma adapter not compute embeddings?**
A: Single Responsibility + swappability. Storage and embedding are separate
ports; we can change the embedder (or precompute/cache vectors) without touching
storage, and vice-versa.

**Q: How is async honoured with sync libraries (sentence-transformers, Chroma)?**
A: Every blocking call is dispatched with `asyncio.to_thread`, so CPU/IO-bound
library work never blocks the event loop.

**Q: Why all-MiniLM-L6-v2?**
A: Free, local (no API cost, no data leaving the box), 384-dim, fast, and good
enough for clause/section retrieval. Its 256-token limit is exactly why the
chunker targets 250 tokens.
