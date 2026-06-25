# Component: Clause-Aware Chunker

**File:** `src/clauseiq/infrastructure/ingestion/chunker.py`
**Tests:** `tests/unit/test_chunker.py` (example + Hypothesis property tests)

## What it does

Turns a unit of source text (a statutory **section**, or a contract **clause**)
into one or more `Chunk` objects sized to fit the embedding model, while keeping
each chunk traceable to the clause it came from. Chunks are what we embed and
store; good chunking is the foundation of good retrieval.

## Why "clause-aware"

Naive fixed-window chunking (e.g. "every 250 tokens") slices straight through
the middle of a clause, so a retrieved fragment loses the legal context that
gives it meaning. This chunker instead treats each **pre-segmented unit as
atomic**: it never merges text across unit boundaries, and stamps every chunk
with `parent_section` (+ `parent_heading`, `chunk_index`, `chunk_count`). So a
retrieved fragment always points back to "Section 23" or "Clause 4".

Input is a `SourceSection(id, text, heading, metadata)`; output is `Chunk[]`.

## The token budget: 250 / 25, and why

Defaults: **250 tokens per chunk, 25-token overlap.**

These are deliberately aligned to the embedding model, **`all-MiniLM-L6-v2`,
whose max sequence length is 256 tokens**. If we chunked at 500 tokens (a
common default), the embedder would **silently truncate** every chunk to 256 —
half the text would never be encoded, and retrieval quality would quietly
degrade with no error. 250/25 keeps each chunk fully within the model's window
with headroom. The values are **configurable** (`Settings`), so a longer-context
embedder can use bigger chunks later.

**Overlap (25 tokens):** consecutive chunks repeat a little trailing context, so
a concept that straddles a chunk boundary still appears whole in at least one
chunk.

## How the packing works

1. Split the unit into sentence-like atoms (on `.!?;` + newlines).
2. Any single sentence longer than the budget is hard-split into word atoms.
3. Greedily pack atoms into windows up to `max_tokens`; when the next atom
   doesn't fit, emit the window and seed the next one with the overlap tail.
4. Each window becomes a `Chunk` with `{section.id}::c{index}` id + metadata.

Guarantee: every chunk fits the budget (except the pathological case of a single
word longer than the budget, which can't be split further).

## Injectable tokenizer (dependency injection)

"Token" is defined by an injected `TokenCounter` (`Callable[[str], int]`):

- **Production:** the embedding model's *own* tokenizer (`build_default_token_counter`
  loads the HF tokenizer for `all-MiniLM-L6-v2`). The budget is then measured in
  exactly the units the embedder uses — not an approximation.
- **Tests:** a cheap word counter (`len(text.split())`), so property tests are
  fast, deterministic, and don't download a model.

This is why we did **not** add `tiktoken` (OpenAI's BPE) — it would be both an
extra dependency and the *wrong* token unit for a MiniLM/BERT model.

## Testing: property-based (Hypothesis)

Beyond example tests, four **invariants** are checked against thousands of
randomly generated inputs:

1. **Budget:** every chunk's token count ≤ `max_tokens`.
2. **Coverage:** every word of the input appears in some chunk (no data loss).
3. **Unique ids:** chunk ids never collide.
4. **Determinism:** chunking the same input twice gives the same result.

Property tests catch edge cases (empty text, one giant sentence, tiny budgets,
zero overlap) that hand-written examples miss.

## Likely interview questions

**Q: How did you pick the chunk size?**
A: It's bounded by the embedder. `all-MiniLM-L6-v2` truncates above 256 tokens,
so I use 250/25 to stay inside the window — otherwise chunks get silently
truncated at embed time. It's configurable for when the embedder changes.

**Q: What does "clause-aware" buy you over fixed-size chunking?**
A: Retrieval relevance and traceability. We never split across a clause, and
every chunk records its parent section, so a flagged risk can cite the exact
clause/section instead of a context-free fragment.

**Q: Why inject the tokenizer?**
A: Testability and correctness. Tests use a trivial word counter (fast,
no model download); production uses the embedder's real tokenizer so the budget
is measured in the embedder's own tokens. DI lets one implementation serve both.

**Q: Why property-based tests here?**
A: Chunking has invariants that must hold for *all* inputs (size bound, no data
loss, determinism). Hypothesis generates adversarial inputs and shrinks failures
to a minimal reproducer — much stronger than a handful of examples.
