"""Unit and property-based tests for the clause-aware chunker.

A simple word-count tokenizer is injected so the token budget is exact and
deterministic (one word == one token), letting the property tests assert hard
invariants without loading a real model.
"""

from __future__ import annotations

import re
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from clauseiq.domain.exceptions import ChunkingError
from clauseiq.infrastructure.ingestion.chunker import Chunker, SourceSection


def word_count(text: str) -> int:
    """One token per whitespace-delimited word."""
    return len(text.split())


def make_chunker(max_tokens: int = 10, overlap_tokens: int = 2) -> Chunker:
    return Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)


# --- Construction validation -------------------------------------------------


@pytest.mark.parametrize(
    ("max_tokens", "overlap_tokens"),
    [(0, 0), (10, 10), (10, 12), (5, -1)],
)
def test_invalid_parameters_raise(max_tokens: int, overlap_tokens: int) -> None:
    with pytest.raises(ChunkingError):
        Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)


# --- Example-based behaviour -------------------------------------------------


def test_empty_text_yields_no_chunks() -> None:
    assert make_chunker().chunk_section(SourceSection(id="s1", text="   \n  ")) == []


def test_short_section_is_a_single_chunk() -> None:
    chunks = make_chunker().chunk_section(SourceSection(id="s1", text="A short clause."))
    assert len(chunks) == 1
    assert chunks[0].id == "s1::c0"
    assert chunks[0].metadata["parent_section"] == "s1"
    assert chunks[0].metadata["chunk_count"] == "1"


def test_metadata_includes_heading_and_propagates_source_metadata() -> None:
    section = SourceSection(
        id="ICA_1872:s23",
        text="The consideration or object of an agreement is lawful.",
        heading="Lawful consideration",
        metadata={"law_code": "ICA_1872"},
    )
    chunk = make_chunker().chunk_section(section)[0]
    assert chunk.metadata["law_code"] == "ICA_1872"
    assert chunk.metadata["parent_heading"] == "Lawful consideration"
    assert chunk.metadata["parent_section"] == "ICA_1872:s23"


def test_long_section_splits_into_multiple_chunks() -> None:
    text = " ".join(f"word{i}" for i in range(45)) + "."
    chunks = make_chunker(max_tokens=10, overlap_tokens=2).chunk_section(
        SourceSection(id="s1", text=text)
    )
    assert len(chunks) > 1
    assert all(word_count(c.text) <= 10 for c in chunks)
    assert [c.metadata["chunk_index"] for c in chunks] == [str(i) for i in range(len(chunks))]


def test_oversized_single_sentence_is_hard_split_by_words() -> None:
    # No sentence terminators -> one giant "sentence" that must be word-split.
    text = " ".join(f"w{i}" for i in range(30))
    chunks = make_chunker(max_tokens=8, overlap_tokens=0).chunk_section(
        SourceSection(id="s1", text=text)
    )
    assert len(chunks) >= 4
    assert all(word_count(c.text) <= 8 for c in chunks)


def test_overlap_repeats_trailing_context() -> None:
    text = " ".join(f"t{i}" for i in range(40))
    chunks = make_chunker(max_tokens=10, overlap_tokens=3).chunk_section(
        SourceSection(id="s1", text=text)
    )
    # With overlap, the start of each chunk after the first repeats words from
    # the end of the previous chunk.
    for previous, nxt in pairwise(chunks):
        prev_words = previous.text.split()
        next_words = nxt.text.split()
        assert next_words[0] in prev_words


# --- Property-based invariants ----------------------------------------------

_words = st.lists(
    st.from_regex(r"[a-z]{1,8}", fullmatch=True),
    min_size=1,
    max_size=200,
)


@st.composite
def _section_and_params(draw: st.DrawFn) -> tuple[SourceSection, int, int]:
    words = draw(_words)
    # Join with a mix of spaces and sentence terminators to exercise both paths.
    separators = draw(st.lists(st.sampled_from([" ", ". ", "; ", "\n"]), min_size=1, max_size=4))
    text = ""
    for index, token in enumerate(words):
        text += token
        if index < len(words) - 1:
            text += separators[index % len(separators)]
    max_tokens = draw(st.integers(min_value=2, max_value=30))
    overlap_tokens = draw(st.integers(min_value=0, max_value=max_tokens - 1))
    return SourceSection(id="s1", text=text), max_tokens, overlap_tokens


@given(_section_and_params())
def test_property_chunks_respect_token_budget(data: tuple[SourceSection, int, int]) -> None:
    section, max_tokens, overlap_tokens = data
    chunker = Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    for chunk in chunker.chunk_section(section):
        # Each atom (word) is <= max_tokens, so every chunk must fit the budget.
        assert word_count(chunk.text) <= max_tokens


@given(_section_and_params())
def test_property_every_word_is_covered(data: tuple[SourceSection, int, int]) -> None:
    section, max_tokens, overlap_tokens = data
    chunker = Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    chunks = chunker.chunk_section(section)
    original_words = set(re.findall(r"[a-z]+", section.text))
    covered_words = {word for chunk in chunks for word in re.findall(r"[a-z]+", chunk.text)}
    assert original_words == covered_words


@given(_section_and_params())
def test_property_chunk_ids_are_unique(data: tuple[SourceSection, int, int]) -> None:
    section, max_tokens, overlap_tokens = data
    chunker = Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    ids = [chunk.id for chunk in chunker.chunk_section(section)]
    assert len(ids) == len(set(ids))


@given(_section_and_params())
def test_property_chunking_is_deterministic(data: tuple[SourceSection, int, int]) -> None:
    section, max_tokens, overlap_tokens = data
    chunker = Chunker(word_count, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    first = [c.text for c in chunker.chunk_section(section)]
    second = [c.text for c in chunker.chunk_section(section)]
    assert first == second
