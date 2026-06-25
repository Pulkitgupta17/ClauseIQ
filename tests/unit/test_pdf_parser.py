"""Unit tests for the PyMuPDF parser.

Small PDFs are synthesised in-memory with PyMuPDF, so these are fast, offline
unit tests with no fixture files.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from clauseiq.domain.exceptions import PDFParsingError
from clauseiq.infrastructure.ingestion.pdf_parser import PyMuPDFParser


def _make_pdf(blocks: list[tuple[str, float]]) -> bytes:
    """Build a one-page PDF; each block is (text, font_size) stacked vertically."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for text, size in blocks:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 24
    data: bytes = doc.tobytes()
    doc.close()
    return data


async def test_parse_bytes_extracts_text_and_pages() -> None:
    pdf = _make_pdf(
        [
            ("23. What considerations and objects are lawful", 16.0),
            (
                "The consideration or object of an agreement is lawful unless forbidden by law.",
                10.0,
            ),
        ]
    )
    document = await PyMuPDFParser().parse(pdf, source_name="ica.pdf")
    assert document.page_count == 1
    assert "considerations and objects are lawful" in document.text
    assert "forbidden by law" in document.text
    assert document.page_text(1) == document.text


async def test_heading_detection_uses_font_size() -> None:
    pdf = _make_pdf(
        [
            ("CHAPTER II OF CONTRACTS", 18.0),
            ("body text that is clearly smaller than the heading above", 9.0),
        ]
    )
    document = await PyMuPDFParser().parse(pdf)
    headings = [block.text for block in document.iter_headings()]
    assert any("CHAPTER II" in heading for heading in headings)
    assert all("body text" not in heading for heading in headings)


async def test_missing_file_raises_pdf_parsing_error() -> None:
    with pytest.raises(PDFParsingError):
        await PyMuPDFParser().parse(Path("/no/such/file.pdf"))


async def test_invalid_bytes_raise_pdf_parsing_error() -> None:
    with pytest.raises(PDFParsingError):
        await PyMuPDFParser().parse(b"this is not a pdf")


async def test_pdf_with_no_text_raises() -> None:
    doc = fitz.open()
    doc.new_page()  # blank page, no text
    blank = doc.tobytes()
    doc.close()
    with pytest.raises(PDFParsingError) as exc_info:
        await PyMuPDFParser().parse(blank)
    assert exc_info.value.message == "no_text_extracted"
