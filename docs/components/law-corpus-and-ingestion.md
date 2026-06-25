# Component: Law Corpus & Ingestion

**Files:** `src/clauseiq/infrastructure/ingestion/law_ingestor.py`,
`scripts/{fetch_ica_source,diff_law_corpus,ingest_laws}.py`,
`data/laws/indian_contract_act_1872.json`
**Tests:** `tests/unit/test_law_ingestor.py`

## The big picture

```
indiacode.nic.in official PDF (consolidated Indian Contract Act, 1872)
        │  scripts/fetch_ica_source.py  (httpx download)
        ▼
PyMuPDFParser  ──►  build_corpus_from_pdf()  ──►  data/laws/…json  (COMMITTED, versioned)
                       (split into 266 sections)         │  source of truth
                                                         │  scripts/ingest_laws.py
                                                         ▼
                                   chunker → embedder → ChromaDB collection "indian_law"
```

## Why a committed JSON, not live scraping

The corpus is **fetched once, reviewed, and committed** as
`data/laws/indian_contract_act_1872.json`. Ingestion reads that file — it never
scrapes at runtime. Why:

- **Reproducible & testable** — CI and every dev get identical data; no network
  flakiness or a moving source breaking builds.
- **Reviewable** — `diff_law_corpus.py` shows a human-readable diff between the
  committed file and a fresh fetch, so a person approves changes before commit.
- **Freshness is explicit** — the JSON header carries `version`
  (`ICA-1872-indiacode-YYYY-MM-DD`), `source_fetched_at`, `effective_date`, and
  a `disclaimer`; per-section records repeat these plus `last_amended` and
  `is_amendment_history_known`.

## Parsing the PDF into sections (the interesting algorithm)

The official PDF starts with an "ARRANGEMENT OF SECTIONS" table of contents,
then the Act body. Naively splitting on "number-dot" fails for three reasons,
each handled deliberately:

1. **The ToC repeats every section number.** → We locate the **body start**
   (the second `PRELIMINARY`) and only parse after it.
2. **Footnotes restart numbering on every page** (`1. Subs. by Act…`). → We walk
   section numbers **strictly increasing** (so a footnote `1.` after section 50
   is ignored) *and* reject lines that begin like footnotes (`Subs.`, `Ins.`,
   `Rep.`, …).
3. **Real headers are messy:** no space after the dot (`3.Communication`),
   definition titles starting with a curly quote (`13. "Consent" defined`), and
   superscript amendment markers glued on (`1[16.` or `1151.` meaning §16/§151).
   → The header regex allows an optional amendment prefix and zero spaces, and a
   number > 266 (impossible for this Act) is repaired by stripping the glued
   footnote digit.

Illustrations and footnotes that sit *between* two section headers are kept with
the **preceding** section, so a section's text stays complete.

Result: **266 sections, 0 of the 238 live sections missed** (76–123 and 239–266
are repealed but still listed as stubs).

## The amendment caveat (a deliberate honesty guardrail)

We can reliably get each section's **text** but not its **amendment dates**. So:
`last_amended` is `null` and `is_amendment_history_known` is `false`. This is
documented in the JSON header `disclaimer`, in the module docstring, and enforced
in code: `amendment_history_note()` returns *"Amendment history not tracked —
verify current law…"* for the frontend to display. We never imply a citation
reflects the current, amended law.

## Ingestion (`ingest_laws.py` → ChromaDB)

`run_ingestion()` loads + validates the JSON (Pydantic `LawCorpus`), turns each
section into a `SourceSection` carrying citation metadata (`law_code`,
`section_number`, `section_title`, `section_text`, freshness fields), chunks them
(clause-aware, 250/25), embeds with all-MiniLM, and upserts into ChromaDB.
**Idempotent**: chunk ids are stable, so re-running upserts in place — no
duplicates.

## Likely interview questions

**Q: Why parse a PDF instead of scraping the section pages?**
A: indiacode is a DSpace repo where the Act's children mix real sections with
state-amendment items — fragile to scrape. The consolidated official PDF is one
authoritative artifact; parsing it is reproducible and reuses our runtime PDF
parser (so a refresh also tests the parser on a real document).

**Q: How do you avoid mistaking footnotes/ToC for sections?**
A: Skip everything before the body marker, walk section numbers strictly
increasing, reject footnote-style lines, and repair amendment-marker-inflated
numbers. Net result is all 238 live sections with zero false splits.

**Q: How is corpus freshness handled?**
A: A `version` string + `source_fetched_at` travel in the JSON and into every
`Citation`. `last_amended` is honestly `null` (not guessed), and the UI shows an
"amendment history not tracked" note. `diff_law_corpus.py` gates refreshes behind
human review.

**Q: Is re-ingesting safe?**
A: Yes — upsert by stable chunk id. Running `ingest_laws.py` twice yields the
same store state.
