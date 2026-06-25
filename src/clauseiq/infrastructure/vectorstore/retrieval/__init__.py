"""Retrieval strategies (Strategy pattern).

``dense`` (semantic, embedding similarity), ``bm25`` (lexical, exact-term), and
``hybrid`` (Reciprocal Rank Fusion of the two) all implement a common
``BaseRetriever`` and satisfy the domain ``Retriever`` port, so they are freely
interchangeable.
"""

from __future__ import annotations
