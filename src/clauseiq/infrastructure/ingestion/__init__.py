"""Ingestion pipeline — turn source documents into retrievable chunks.

Stages: parse (PDF/structured source) -> chunk (clause-aware) -> load (into the
vector store). Each stage has typed I/O and raises a subclass of
:class:`~clauseiq.domain.exceptions.IngestionError` on failure.
"""

from __future__ import annotations
