"""Unit tests for the law corpus schema, PDF splitter, and ingestion."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import pytest

from clauseiq.domain.entities import Chunk
from clauseiq.domain.exceptions import IngestionError
from clauseiq.infrastructure.ingestion.chunker import Chunker
from clauseiq.infrastructure.ingestion.law_ingestor import (
    LawCorpus,
    build_corpus_from_pdf,
    corpus_to_source_sections,
    ingest_corpus,
    load_corpus,
)
from clauseiq.infrastructure.ingestion.pdf_parser import ParsedBlock, ParsedDocument

# A miniature "Act" exercising: ToC skipping, body detection, monotonic section
# numbering, footnote rejection, and illustration attachment.
_MINI_ACT = """\
ARRANGEMENT OF SECTIONS
1. Short title.
2. Foo defined.
3. Bar provision.

PRELIMINARY

1. Short title.—This Act may be called the Test Act, 1900.

2. Foo defined.—"Foo" means bar for the purposes of this Act.
Illustration
(a) A gives B a foo; this is a valid foo.
1. Subs. by Act 7 of 1901 for certain words.

3. Bar provision.—Every bar shall be regulated as follows and no otherwise.
"""


def _doc(text: str) -> ParsedDocument:
    block = ParsedBlock(text=text, page_number=1, font_size=10.0, bbox=(0.0, 0.0, 1.0, 1.0))
    return ParsedDocument(blocks=(block,), page_count=1)


def _corpus_from_mini() -> LawCorpus:
    return build_corpus_from_pdf(
        _doc(_MINI_ACT),
        source_url="http://example.test/act.pdf",
        fetched_at=date(2026, 6, 25),
        version="TEST-1",
    )


def test_splitter_finds_body_sections_only() -> None:
    corpus = _corpus_from_mini()
    numbers = [s.section_number for s in corpus.sections]
    assert numbers == ["1", "2", "3"]  # ToC entries are not duplicated


def test_splitter_titles_and_freshness_fields() -> None:
    corpus = _corpus_from_mini()
    by_num = {s.section_number: s for s in corpus.sections}
    assert by_num["1"].section_title == "Short title"
    assert by_num["2"].section_title == "Foo defined"
    assert by_num["1"].effective_date == date(1872, 9, 1)
    assert by_num["1"].last_amended is None
    assert by_num["1"].is_amendment_history_known is False
    assert by_num["1"].source_fetched_at == date(2026, 6, 25)


def test_splitter_attaches_illustration_and_footnote_to_parent() -> None:
    section_two = {s.section_number: s for s in _corpus_from_mini().sections}["2"]
    # Illustration and the page footnote fall between section 2 and 3, so they
    # belong to section 2 — not promoted to new sections.
    assert "Illustration" in section_two.section_text
    assert "valid foo" in section_two.section_text
    assert "Subs. by Act 7 of 1901" in section_two.section_text


def test_splitter_raises_without_body_marker() -> None:
    with pytest.raises(IngestionError):
        build_corpus_from_pdf(
            _doc("just some text with no body marker and 1. not a real act"),
            source_url="x",
            fetched_at=date(2026, 6, 25),
            version="v",
        )


def test_corpus_to_source_sections_metadata() -> None:
    sources = corpus_to_source_sections(_corpus_from_mini())
    first = sources[0]
    assert first.id == "ICA_1872:s1"
    assert first.metadata["section_number"] == "1"
    assert first.metadata["law_code"] == "ICA_1872"
    assert first.metadata["effective_date"] == "1872-09-01"
    assert first.metadata["is_amendment_history_known"] == "false"
    assert "last_amended" not in first.metadata  # omitted when null (Chroma-safe)


def test_load_corpus_roundtrip(tmp_path: Path) -> None:
    corpus = _corpus_from_mini()
    path = tmp_path / "corpus.json"
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    loaded = load_corpus(path)
    assert loaded.version == "TEST-1"
    assert len(loaded.sections) == 3


def test_load_corpus_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IngestionError):
        load_corpus(path)


def test_load_corpus_schema_violation_raises(tmp_path: Path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"version": "v"}), encoding="utf-8")  # missing required fields
    with pytest.raises(IngestionError):
        load_corpus(path)


# --- ingest_corpus with fakes ------------------------------------------------


class _FakeEmbedder:
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 0.0, 0.0] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0, 0.0]


class _RecordingStore:
    def __init__(self) -> None:
        self.added: list[Chunk] = []

    async def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        assert len(chunks) == len(embeddings)
        self.added.extend(chunks)

    async def query(
        self, embedding: Sequence[float], k: int, *, where: Mapping[str, str] | None = None
    ) -> list[Chunk]:
        return []

    async def get_all(self, *, where: Mapping[str, str] | None = None) -> list[Chunk]:
        return list(self.added)

    async def count(self) -> int:
        return len(self.added)


async def test_ingest_corpus_chunks_embeds_and_stores() -> None:
    store = _RecordingStore()
    chunker = Chunker(lambda t: len(t.split()), max_tokens=20, overlap_tokens=2)
    report = await ingest_corpus(
        _corpus_from_mini(), store=store, embedder=_FakeEmbedder(), chunker=chunker
    )
    assert report.sections == 3
    assert report.chunks >= 3
    assert len(store.added) == report.chunks
    assert all(c.metadata["law_code"] == "ICA_1872" for c in store.added)
