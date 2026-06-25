"""Repositories — domain-friendly facades over the vector store.

A repository hides storage details (ChromaDB, retrieval strategies) behind the
domain repository ports, returning domain entities (``Citation``, ``ScoredChunk``)
and ``Result`` values rather than raw infrastructure types.
"""

from __future__ import annotations
