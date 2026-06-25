"""Infrastructure-facing vector-store interfaces.

The canonical contracts live in :mod:`clauseiq.domain.ports` (``Embedder`` and
``VectorStore``). They are re-exported here so infrastructure code and tests can
import the storage interfaces from one local place, and this module is the seam
where any storage-only base helper would live if one were needed.
"""

from __future__ import annotations

from clauseiq.domain.ports import Embedder, VectorStore

__all__ = ["Embedder", "VectorStore"]
