# Component: Domain Layer

**Files:** `src/clauseiq/domain/{result,exceptions,value_objects,entities,ports}.py`
**Tests:** `tests/unit/test_{result,exceptions,value_objects,entities,ports}.py` (100% coverage)

## What it is

The pure core of the app. No third-party dependencies, no I/O, no framework
code — just the business vocabulary and the interfaces the rest of the system
implements. If you deleted FastAPI, ChromaDB, and Gemini, this layer would still
compile and its tests would still pass.

## The pieces

### 1. `Result[T, E]` — explicit expected failures (`result.py`)

A tiny `Ok`/`Err` type (inspired by Rust). Functions that can fail *in a normal,
expected way* return `Result` instead of raising:

```python
async def retrieve(query: str) -> Result[list[Chunk], RetrievalError]:
    ...
    if not hits:
        return Err(RetrievalError("no_results"))
    return Ok(hits)
```

- `Ok(value)` / `Err(error)` — the two variants (frozen dataclasses).
- Helpers: `map`, `map_err`, `and_then`, `unwrap`, `unwrap_or`, `unwrap_err`.
- Pattern-matchable: `match result: case Ok(v): ... case Err(e): ...`.

**Why:** raising for expected paths hides them from the type signature and is
easy to forget. `Result` puts "this can fail, and here's how" right in the
return type, so the compiler/`mypy` forces callers to handle it.

### 2. Exceptions — for bugs and invariant violations (`exceptions.py`)

A hierarchy rooted at `ClauseIQError` (carries `message`, machine `code`,
`cause`, and structured `context`). Subclasses: `RetrievalError`,
`LowConfidenceError`, `PDFParsingError`, `ChunkingError`, `VectorStoreError`,
`EmbeddingError`, `RepositoryError`, `ValidationError`, …

**Why two mechanisms?** `Result` = *expected* failure (handle it).
Exception = *unexpected* failure / programmer error (let it bubble, log it).
Everything derives from `ClauseIQError`, so we `except ClauseIQError` — never a
bare `except`.

### 3. Value objects — closed vocabularies (`value_objects.py`)

- `Severity` — `IntEnum` (`INFO<LOW<MEDIUM<HIGH<CRITICAL`). **IntEnum on
  purpose** so flags sort by severity for free and `.normalized_score` gives a
  0–1 number for the UI gauge.
- `ClauseType` — `str` enum (`SECURITY_DEPOSIT`, `LOCK_IN`, `NON_COMPETE`,
  `ARBITRATION`, …) oriented at Indian rental/employment/freelance contracts.
- `Jurisdiction` — `IN-MH`/`IN-DL`/`IN-KA` (matches the API contract).
- `LawCode` — statutes a citation can point to (ICA 1872, SRA 1963, CPA 2019,
  state rent acts). `.full_title` gives the canonical name (named `full_title`,
  not `title`, because `str` already has a `.title()` method).

### 4. Entities — the nouns (`entities.py`)

Frozen dataclasses, validated in `__post_init__` so an invalid one can't exist:

- `Chunk` / `ScoredChunk` — a retrievable piece of text (+ relevance score).
- `Citation` — a reference to a law section, **with freshness fields**
  (`effective_date`, `last_amended`, `source_fetched_at`) so users see how
  current the cited law is.
- `Clause` — one clause from a contract (`clause_type` is `None` until analyzed).
- `RiskFlag` — severity + rationale + citations + confidence for a clause.
- `Contract` — raw text + extracted clauses + jurisdiction.

**Why frozen?** Immutability makes them safe to pass between concurrent agents
and trivial to reason about — no spooky action at a distance.

### 5. Ports — the interfaces (`ports.py`)

`Protocol` classes: `Embedder`, `VectorStore`, `Retriever`, `LawRepository`.
The domain/application depend on *these shapes*; infrastructure provides the
real implementations. This is **Dependency Inversion** — the inner layer owns
the interface, the outer layer conforms to it.

## Likely interview questions

**Q: Why a `Result` type instead of just exceptions?**
A: To distinguish *expected* failures (no results, low confidence) from *bugs*.
Expected failures belong in the type signature so callers must handle them;
exceptions are for the unexpected. It also makes failure handling composable
(`map`/`and_then`) instead of nested try/except.

**Q: Why is the domain layer dependency-free?**
A: It encodes business rules that shouldn't change when we swap a database or an
LLM. Keeping it pure means we can unit-test it with no mocks/I/O (hence 100%
coverage), and the dependency rule (inner knows nothing of outer) stays intact.

**Q: Why `Protocol` for ports instead of abstract base classes?**
A: Structural typing — an adapter satisfies the port just by having the right
methods, no inheritance coupling. It keeps infrastructure from importing domain
base classes just to subclass them, and plays well with duck-typed test fakes.

**Q: Why `IntEnum` for `Severity`?**
A: Severity is inherently ordered. `IntEnum` gives ordering and sortability for
free (`max(flags, key=...).severity`), plus a numeric basis for the UI gauge,
without a separate ranking table.
