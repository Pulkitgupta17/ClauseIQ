"""Vector store, embeddings, and retrieval strategies.

``embedder.py`` produces dense vectors, ``chroma.py`` persists/queries them, and
``retrieval/`` holds interchangeable retrieval strategies (BM25, dense, hybrid)
behind a common base — the Strategy pattern.
"""

from __future__ import annotations
