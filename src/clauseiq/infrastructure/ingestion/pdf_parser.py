"""PDF parsing behind a strategy port.

``BasePDFParser`` is the port; ``PyMuPDFParser`` is the only adapter for now and
is the right default — PyMuPDF gives fast, high-fidelity text extraction with
per-span font sizes, which is enough to preserve section/clause structure for
born-digital legal PDFs (the Indian Contract Act, typical contracts).

NOTE: A second adapter, ``UnstructuredParser`` (the ``unstructured`` library),
is intended to slot in here when OCR or complex-layout/table extraction is
needed — likely M3 if eval cases include scanned contracts, otherwise post-MVP.
It would implement the same ``BasePDFParser`` port, so nothing downstream
changes. Kept out of M1 to avoid a heavy dependency we don't yet exercise.

Structure preservation: rather than returning a flat string, the parser returns
a :class:`ParsedDocument` of blocks, each with its page, bounding box, and
dominant font size. Font size is the signal downstream code (e.g. the law
ingestor) uses to tell section headings from body text.
"""

from __future__ import annotations

import asyncio
import statistics
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any  # Any: PyMuPDF's get_text("dict") is untyped

from clauseiq.domain.exceptions import PDFParsingError
from clauseiq.logging_config import get_logger

if TYPE_CHECKING:
    import fitz

log = get_logger(__name__)

# A block whose font is >= this ratio of the body median is treated as a heading.
_HEADING_FONT_RATIO = 1.15


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """A contiguous text block extracted from a PDF page."""

    text: str
    page_number: int  # 1-based
    font_size: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """The structured result of parsing a PDF."""

    blocks: tuple[ParsedBlock, ...]
    page_count: int
    title: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Full document text, blocks joined in reading order by blank lines."""
        return "\n\n".join(block.text for block in self.blocks)

    def page_text(self, page_number: int) -> str:
        """Text of a single 1-based page."""
        return "\n\n".join(b.text for b in self.blocks if b.page_number == page_number)

    def body_font_size(self) -> float:
        """Median block font size — the baseline for heading detection."""
        sizes = [block.font_size for block in self.blocks if block.font_size > 0]
        return statistics.median(sizes) if sizes else 0.0

    def iter_headings(self, *, ratio: float = _HEADING_FONT_RATIO) -> Iterator[ParsedBlock]:
        """Yield blocks whose font size suggests they are headings."""
        baseline = self.body_font_size()
        if baseline <= 0:
            return
        threshold = baseline * ratio
        for block in self.blocks:
            if block.font_size >= threshold:
                yield block


class BasePDFParser(ABC):
    """Port for PDF parsers (Strategy pattern)."""

    @abstractmethod
    async def parse(
        self, source: Path | bytes, *, source_name: str | None = None
    ) -> ParsedDocument:
        """Parse a PDF from a path or raw bytes into a :class:`ParsedDocument`.

        Raises:
            PDFParsingError: If the PDF cannot be opened or read.
        """
        raise NotImplementedError


class PyMuPDFParser(BasePDFParser):
    """PDF parser backed by PyMuPDF (``fitz``)."""

    async def parse(
        self, source: Path | bytes, *, source_name: str | None = None
    ) -> ParsedDocument:
        """Parse a PDF (path or bytes) off the event loop via a worker thread."""
        return await asyncio.to_thread(self._parse_sync, source, source_name)

    def _parse_sync(self, source: Path | bytes, source_name: str | None) -> ParsedDocument:
        name = source_name or (str(source) if isinstance(source, Path) else "<bytes>")
        try:
            document = self._open(source)
        except Exception as exc:  # external boundary
            raise PDFParsingError("open_failed", cause=exc, source=name) from exc

        try:
            blocks = tuple(self._extract_blocks(document))
            page_count = document.page_count
            metadata = {k: str(v) for k, v in (document.metadata or {}).items() if v}
        except Exception as exc:  # external boundary
            raise PDFParsingError("extract_failed", cause=exc, source=name) from exc
        finally:
            document.close()

        if not blocks:
            raise PDFParsingError("no_text_extracted", source=name, page_count=page_count)

        log.info("pdf_parsed", source=name, pages=page_count, blocks=len(blocks))
        return ParsedDocument(
            blocks=blocks,
            page_count=page_count,
            title=metadata.get("title") or None,
            metadata=metadata,
        )

    @staticmethod
    def _open(source: Path | bytes) -> fitz.Document:
        import fitz

        if isinstance(source, Path):
            if not source.exists():
                raise FileNotFoundError(source)
            return fitz.open(source)
        return fitz.open(stream=source, filetype="pdf")

    @staticmethod
    def _extract_blocks(document: fitz.Document) -> Iterator[ParsedBlock]:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                lines = block.get("lines")
                if not lines:  # image block or empty
                    continue
                text, font_size = PyMuPDFParser._render_block(lines)
                if text.strip():
                    raw_bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    yield ParsedBlock(
                        text=text.strip(),
                        page_number=page_index + 1,
                        font_size=font_size,
                        bbox=(
                            float(raw_bbox[0]),
                            float(raw_bbox[1]),
                            float(raw_bbox[2]),
                            float(raw_bbox[3]),
                        ),
                    )

    @staticmethod
    def _render_block(lines: Sequence[Mapping[str, Any]]) -> tuple[str, float]:
        """Join a block's lines into text and return its dominant font size."""
        line_texts: list[str] = []
        sizes: list[float] = []
        for line in lines:
            spans = line.get("spans", [])
            span_texts: list[str] = []
            for span in spans:
                span_text = str(span.get("text", ""))
                span_texts.append(span_text)
                size = span.get("size")
                if isinstance(size, int | float) and span_text.strip():
                    sizes.append(float(size))
            line_texts.append("".join(span_texts))
        text = "\n".join(line_texts)
        dominant = max(sizes) if sizes else 0.0
        return text, dominant


__all__ = [
    "BasePDFParser",
    "ParsedBlock",
    "ParsedDocument",
    "PyMuPDFParser",
]
