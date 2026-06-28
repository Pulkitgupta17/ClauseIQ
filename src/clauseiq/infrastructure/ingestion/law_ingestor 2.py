"""Indian Contract Act corpus: schema, PDF splitting, and ingestion.

Two responsibilities live here:

1. **Build** the committed JSON corpus from the official consolidated Act PDF
   (:func:`build_corpus_from_pdf`) — used by ``scripts/fetch_ica_source.py``.
2. **Ingest** that JSON corpus into ChromaDB (:func:`run_ingestion`) — the
   data-pipeline bootstrap, also the ``clauseiq-ingest-laws`` console script.

Corpus freshness / amendment caveat
-----------------------------------
``effective_date`` is the Act's commencement (1 Sep 1872), corpus-wide.
**Per-section ``last_amended`` is ``null`` wherever an amendment date cannot be
reliably derived from the source**, and ``is_amendment_history_known`` is
``False``. Amendment history is NOT tracked here — downstream citation code must
surface "amendment history not tracked" rather than imply the text is current.
See :const:`AMENDMENT_DISCLAIMER`.

PDF splitting strategy
----------------------
The official PDF begins with an "ARRANGEMENT OF SECTIONS" table of contents,
then the body. We locate the body, then walk **strictly increasing** section
numbers (1..266; 76-123 and 239-266 are repealed but still listed). Footnotes
restart numbering per page and are rejected by a phrase filter; superscript
amendment markers glued to section numbers (e.g. ``1[16.`` or ``1151.``) are
normalised. Illustrations and footnotes between two section headers stay with
the preceding section.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from clauseiq.config import settings
from clauseiq.domain.exceptions import IngestionError
from clauseiq.domain.ports import Embedder, VectorStore
from clauseiq.infrastructure.ingestion.chunker import (
    Chunker,
    SourceSection,
    build_default_chunker,
)
from clauseiq.infrastructure.ingestion.pdf_parser import ParsedDocument, PyMuPDFParser
from clauseiq.infrastructure.vectorstore.chroma import build_law_vector_store
from clauseiq.infrastructure.vectorstore.embedder import SentenceTransformerEmbedder
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

ICA_LAW_CODE = "ICA_1872"
ICA_EFFECTIVE_DATE = date(1872, 9, 1)
ICA_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf"
ICA_MAX_SECTION = 266

AMENDMENT_DISCLAIMER = (
    "Per-section 'last_amended' is null where an amendment date could not be reliably "
    "derived from the source. Amendment history is NOT tracked in this corpus "
    "(is_amendment_history_known=false). Verify current law for time-sensitive matters."
)

# --- Section-header detection ------------------------------------------------
# These patterns intentionally contain non-ASCII characters that occur in the
# real legal text (curly quotes around defined terms, en/em dashes after marginal
# notes), so RUF001 "ambiguous unicode" is suppressed where they appear.
# Line start, optional amendment marker ("1[" / "§"), section number, optional
# space, then a title-start char (letter, quote, bracket, paren).
_HEADER = re.compile(
    r'(?m)^[ \t]*(?:\d{1,2}\s*\[\s*)?(?:§[ \t]*)?(\d{1,4})\.\s*(?=[A-Za-z"“‘\'(\[])'  # noqa: RUF001
)
# Footnotes restart per page; reject lines that begin like amendment footnotes.
_FOOTNOTE = re.compile(
    r'^[“"\'\[]?\s*(Subs\.|Ins\.|Omitted|Added|Rep\.|The words|The word|Earlier|'
    r"Cl\.|w\.e\.f|Sub-section|Certain|These words|Now|Clause|Ibid|s\.\s|Section)",
    re.IGNORECASE,
)
# Running page furniture to drop from section text.
_NOISE_LINE = re.compile(r"^(THE INDIAN CONTRACT ACT,?\s*1872|\d{1,3})$", re.IGNORECASE)
_BODY_MARKERS = ("PRELIMINARY", "It is hereby enacted as follows")


class LawSection(BaseModel):
    """One statutory section as stored in the committed corpus JSON."""

    section_number: str = Field(min_length=1)
    section_title: str
    section_text: str = Field(min_length=1)
    effective_date: date | None = None
    last_amended: date | None = None
    source_fetched_at: date | None = None
    version: str = "unversioned"
    is_amendment_history_known: bool = False


class LawCorpus(BaseModel):
    """The committed law corpus: header metadata + sections.

    The ``disclaimer`` is persisted into the JSON header so the amendment caveat
    travels with the data.
    """

    law_code: str = ICA_LAW_CODE
    statute_title: str = "Indian Contract Act, 1872"
    version: str
    source_url: str
    source_fetched_at: date
    effective_date: date
    license_note: str = (
        "Government of India legal text (public domain under s.52(1)(q), Copyright Act 1957)."
    )
    disclaimer: str = AMENDMENT_DISCLAIMER
    sections: list[LawSection]


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Outcome of an ingestion run."""

    sections: int
    chunks: int


# --- PDF -> corpus -----------------------------------------------------------


def _locate_body_start(text: str) -> int:
    """Return the offset where the Act body begins (after the ToC)."""
    offsets = [text.rfind(marker) for marker in _BODY_MARKERS]
    offsets = [offset for offset in offsets if offset >= 0]
    if not offsets:
        raise IngestionError("body_start_not_found", markers=_BODY_MARKERS)
    return max(offsets)


def _normalise_section_number(raw: int, last: int) -> int | None:
    """Map a raw header number to a valid, increasing section number, or None.

    Recovers numbers inflated by a glued footnote digit (``1151`` -> ``151``).
    """
    if raw <= ICA_MAX_SECTION:
        return raw if raw > last else None
    digits = str(raw)
    for cut in (1, 2):
        if len(digits) > cut:
            candidate = int(digits[cut:])
            if last < candidate <= ICA_MAX_SECTION:
                return candidate
    return None


def _clean_section_text(span: str) -> str:
    """Drop running page furniture and normalise blank runs in a section span."""
    kept = [line.rstrip() for line in span.splitlines() if not _NOISE_LINE.match(line.strip())]
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_title(span: str) -> str:
    """Extract the marginal-note title from the start of a section span."""
    body = _HEADER.sub("", span, count=1).lstrip()
    match = re.match(r"(.+?)\.\s*[—–-]", body, re.DOTALL) or re.match(  # noqa: RUF001
        r"(.+?)\.(?:\s|$)", body, re.DOTALL
    )
    title = match.group(1) if match else body[:80]
    title = re.sub(r"\s+", " ", title).strip()
    if title.startswith("["):
        return "Repealed"
    return title or "Untitled"


def build_corpus_from_pdf(
    document: ParsedDocument,
    *,
    source_url: str,
    fetched_at: date,
    version: str,
) -> LawCorpus:
    """Split the parsed official Act PDF into a :class:`LawCorpus`.

    Raises:
        IngestionError: If the body cannot be located or no sections are found.
    """
    text = document.text
    body = text[_locate_body_start(text) :]

    accepted: list[tuple[int, int]] = []
    last = 0
    for match in _HEADER.finditer(body):
        following = body[match.end() : match.end() + 50].lstrip()
        if _FOOTNOTE.match(following):
            continue
        number = _normalise_section_number(int(match.group(1)), last)
        if number is None:
            continue
        accepted.append((number, match.start()))
        last = number

    if not accepted:
        raise IngestionError("no_sections_parsed", source=source_url)

    sections: list[LawSection] = []
    for index, (number, start) in enumerate(accepted):
        end = accepted[index + 1][1] if index + 1 < len(accepted) else len(body)
        span = _clean_section_text(body[start:end])
        if not span:
            continue
        sections.append(
            LawSection(
                section_number=str(number),
                section_title=_extract_title(span),
                section_text=span,
                effective_date=ICA_EFFECTIVE_DATE,
                last_amended=None,
                source_fetched_at=fetched_at,
                version=version,
                is_amendment_history_known=False,
            )
        )

    log.info("corpus_built", sections=len(sections), source=source_url, version=version)
    return LawCorpus(
        version=version,
        source_url=source_url,
        source_fetched_at=fetched_at,
        effective_date=ICA_EFFECTIVE_DATE,
        sections=sections,
    )


async def fetch_corpus_from_source(
    url: str = ICA_SOURCE_URL,
    *,
    fetched_at: date,
    request_timeout: float = 60.0,
) -> LawCorpus:
    """Download the official Act PDF and build a :class:`LawCorpus` from it.

    Parses the PDF with the same :class:`PyMuPDFParser` used at runtime, so a
    refresh also validates the parser against the real document.

    Raises:
        IngestionError: If the download fails or the PDF cannot be parsed/split.
    """
    try:
        async with httpx.AsyncClient(timeout=request_timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            pdf_bytes = response.content
    except httpx.HTTPError as exc:
        raise IngestionError("source_download_failed", cause=exc, url=url) from exc

    document = await PyMuPDFParser().parse(pdf_bytes, source_name=url)
    version = f"ICA-1872-indiacode-{fetched_at.isoformat()}"
    return build_corpus_from_pdf(document, source_url=url, fetched_at=fetched_at, version=version)


# --- corpus -> ChromaDB ------------------------------------------------------


def load_corpus(path: Path) -> LawCorpus:
    """Load and validate the committed corpus JSON."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IngestionError("corpus_read_failed", cause=exc, path=str(path)) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IngestionError("corpus_parse_failed", cause=exc, path=str(path)) from exc
    try:
        return LawCorpus.model_validate(data)
    except PydanticValidationError as exc:
        raise IngestionError("corpus_invalid", cause=exc, path=str(path)) from exc


def corpus_to_source_sections(corpus: LawCorpus) -> list[SourceSection]:
    """Turn corpus sections into chunker inputs with citation-bearing metadata."""
    sources: list[SourceSection] = []
    for section in corpus.sections:
        metadata: dict[str, str] = {
            "law_code": corpus.law_code,
            "section_number": section.section_number,
            "section_title": section.section_title,
            "section_text": section.section_text,
            "source_url": corpus.source_url,
            "corpus_version": section.version,
            "is_amendment_history_known": str(section.is_amendment_history_known).lower(),
        }
        if section.effective_date:
            metadata["effective_date"] = section.effective_date.isoformat()
        if section.source_fetched_at:
            metadata["source_fetched_at"] = section.source_fetched_at.isoformat()
        if section.last_amended:
            metadata["last_amended"] = section.last_amended.isoformat()
        sources.append(
            SourceSection(
                id=f"{corpus.law_code}:s{section.section_number}",
                text=section.section_text,
                heading=section.section_title,
                metadata=metadata,
            )
        )
    return sources


async def ingest_corpus(
    corpus: LawCorpus,
    *,
    store: VectorStore,
    embedder: Embedder,
    chunker: Chunker,
) -> IngestReport:
    """Chunk, embed, and store a corpus into the vector store."""
    sources = corpus_to_source_sections(corpus)
    chunks = chunker.chunk_sections(sources)
    if not chunks:
        raise IngestionError("no_chunks_produced", sections=len(sources))
    embeddings = await embedder.embed_documents([chunk.text for chunk in chunks])
    await store.add(chunks, embeddings)
    report = IngestReport(sections=len(sources), chunks=len(chunks))
    log.info("corpus_ingested", sections=report.sections, chunks=report.chunks)
    return report


async def run_ingestion(*, corpus_path: Path | None = None) -> IngestReport:
    """Load the committed corpus and ingest it into ChromaDB (settings-wired)."""
    corpus = load_corpus(corpus_path or settings.law_corpus_path)
    store = build_law_vector_store()
    embedder = SentenceTransformerEmbedder()
    chunker = build_default_chunker()
    return await ingest_corpus(corpus, store=store, embedder=embedder, chunker=chunker)


def main() -> None:
    """Console entry point (``clauseiq-ingest-laws``)."""
    from clauseiq.logging_config import configure_logging

    configure_logging()
    report = asyncio.run(run_ingestion())
    log.info("ingestion_complete", sections=report.sections, chunks=report.chunks)


__all__ = [
    "AMENDMENT_DISCLAIMER",
    "IngestReport",
    "LawCorpus",
    "LawSection",
    "build_corpus_from_pdf",
    "corpus_to_source_sections",
    "fetch_corpus_from_source",
    "ingest_corpus",
    "load_corpus",
    "main",
    "run_ingestion",
]
