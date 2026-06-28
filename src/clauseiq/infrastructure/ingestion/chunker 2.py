"""Clause-aware, token-budgeted chunker.

Why clause-aware
----------------
Naive fixed-window chunking splits mid-clause, which destroys the legal meaning
we later retrieve on. This chunker treats each pre-segmented unit (a statutory
section, or a contract clause) as the atomic context: it never merges text
across unit boundaries, packs sentences greedily up to a token budget, and
stamps every chunk with its ``parent_section`` so a retrieved fragment can
always be traced back to the clause it came from.

Token budget and the embedding model
-------------------------------------
The defaults are **250 tokens with 25 overlap**, deliberately aligned to the
embedding model (``all-MiniLM-L6-v2``), whose maximum sequence length is **256
tokens**. Chunking larger than that would cause silent truncation at embed time
— half of a 500-token chunk would never be encoded. The size is configurable for
when a longer-context embedder is swapped in.

Tokenizer injection
--------------------
"Token" is defined by an injected :data:`TokenCounter`. In production this is
the embedding model's own tokenizer (so the budget is measured in exactly the
units the embedder uses); tests inject a cheap word counter to stay fast and
deterministic. See :func:`build_default_token_counter`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TypeAlias

from clauseiq.domain.entities import Chunk
from clauseiq.domain.exceptions import ChunkingError

TokenCounter: TypeAlias = Callable[[str], int]
"""Counts the number of tokens in a string. Injected into :class:`Chunker`."""

# Split on sentence terminators followed by whitespace, and on hard line breaks.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+|\n+")


@dataclass(frozen=True, slots=True)
class SourceSection:
    """A pre-segmented unit of source text to be chunked.

    Attributes:
        id: Stable identifier for the unit (e.g. ``"ICA_1872:s23"`` or
            ``"contract:cl4"``). Becomes the chunks' ``parent_section`` and the
            stem of each chunk id.
        text: The unit's full text.
        heading: Optional human-facing heading carried into chunk metadata.
        metadata: Extra string-valued metadata propagated onto every chunk
            produced from this unit.
    """

    id: str
    text: str
    heading: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into trimmed, non-empty sentence-like fragments."""
    return [fragment.strip() for fragment in _SENTENCE_BOUNDARY.split(text) if fragment.strip()]


class Chunker:
    """Packs source sections into token-budgeted, overlapping :class:`Chunk` objects.

    Args:
        token_counter: Strategy that counts tokens in a string.
        max_tokens: Maximum tokens per chunk (must be >= 1).
        overlap_tokens: Tokens of trailing context repeated at the start of the
            next chunk (must be >= 0 and strictly less than ``max_tokens``).

    Raises:
        ChunkingError: If the chunk parameters are invalid.
    """

    def __init__(
        self,
        token_counter: TokenCounter,
        *,
        max_tokens: int = 250,
        overlap_tokens: int = 25,
    ) -> None:
        if max_tokens < 1:
            raise ChunkingError("max_tokens must be >= 1", max_tokens=max_tokens)
        if overlap_tokens < 0:
            raise ChunkingError("overlap_tokens must be >= 0", overlap_tokens=overlap_tokens)
        if overlap_tokens >= max_tokens:
            raise ChunkingError(
                "overlap_tokens must be < max_tokens",
                overlap_tokens=overlap_tokens,
                max_tokens=max_tokens,
            )
        self._count = token_counter
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk_sections(self, sections: Iterable[SourceSection]) -> list[Chunk]:
        """Chunk many sections, preserving order."""
        chunks: list[Chunk] = []
        for section in sections:
            chunks.extend(self.chunk_section(section))
        return chunks

    def chunk_section(self, section: SourceSection) -> list[Chunk]:
        """Chunk a single section into token-budgeted, overlapping chunks.

        Returns an empty list for empty/whitespace-only text (no empty chunks
        are ever produced). Each chunk carries ``parent_section`` and chunk
        index/count metadata so retrieved fragments stay traceable.
        """
        text = section.text.strip()
        if not text:
            return []

        atoms = self._to_atoms(text)
        windows = self._pack(atoms)
        total = len(windows)
        return [
            Chunk(
                id=f"{section.id}::c{index}",
                text=window,
                metadata=self._chunk_metadata(section, index, total),
            )
            for index, window in enumerate(windows)
        ]

    def _to_atoms(self, text: str) -> list[str]:
        """Break text into atoms (sentences), hard-splitting oversized sentences.

        Every returned atom is guaranteed to fit the budget on its own, except a
        single word longer than ``max_tokens`` (which cannot be split further).
        """
        atoms: list[str] = []
        for sentence in _split_sentences(text):
            if self._count(sentence) <= self.max_tokens:
                atoms.append(sentence)
            else:
                atoms.extend(sentence.split())
        return atoms

    def _pack(self, atoms: Sequence[str]) -> list[str]:
        """Greedily pack atoms into windows that respect the token budget."""
        windows: list[str] = []
        current: list[str] = []

        for atom in atoms:
            if not current:
                current = [atom]
                continue
            if self._count(_join([*current, atom])) <= self.max_tokens:
                current.append(atom)
                continue
            # Atom does not fit: flush the current window and start a new one,
            # seeding it with as much trailing overlap as the budget allows.
            windows.append(_join(current))
            tail = self._overlap_tail(current)
            seeded = [*tail, atom]
            current = seeded if self._count(_join(seeded)) <= self.max_tokens else [atom]

        if current:
            windows.append(_join(current))
        return windows

    def _overlap_tail(self, atoms: Sequence[str]) -> list[str]:
        """Longest suffix of ``atoms`` whose joined token count <= overlap budget."""
        if self.overlap_tokens == 0:
            return []
        tail: list[str] = []
        for atom in reversed(atoms):
            if self._count(_join([atom, *tail])) <= self.overlap_tokens:
                tail.insert(0, atom)
            else:
                break
        return tail

    @staticmethod
    def _chunk_metadata(section: SourceSection, index: int, total: int) -> dict[str, str]:
        metadata = dict(section.metadata)
        metadata["parent_section"] = section.id
        metadata["chunk_index"] = str(index)
        metadata["chunk_count"] = str(total)
        if section.heading:
            metadata["parent_heading"] = section.heading
        return metadata


def _join(atoms: Sequence[str]) -> str:
    """Join atoms with single spaces (chunk text is whitespace-normalised)."""
    return " ".join(atoms)


@lru_cache(maxsize=4)
def build_default_token_counter(model_name: str) -> TokenCounter:
    """Build a token counter backed by the embedding model's own tokenizer.

    The tokenizer is loaded once per model (cached). ``add_special_tokens`` is
    disabled so the count reflects content tokens only.

    Args:
        model_name: A Hugging Face / sentence-transformers model id.

    Returns:
        A :data:`TokenCounter` measuring content tokens for that model.
    """
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return count


def build_default_chunker() -> Chunker:
    """Wire a :class:`Chunker` from application settings and the model tokenizer."""
    from clauseiq.config import settings

    return Chunker(
        build_default_token_counter(settings.embedding_model),
        max_tokens=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )


__all__ = [
    "Chunker",
    "SourceSection",
    "TokenCounter",
    "build_default_chunker",
    "build_default_token_counter",
]
