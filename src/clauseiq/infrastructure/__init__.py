"""Infrastructure layer — adapters to the outside world.

Concrete implementations of the domain ports (vector stores, retrievers,
embedders, LLM clients, repositories, ingestion). Outer layer: it may import
from :mod:`clauseiq.domain` and :mod:`clauseiq.application`, never the reverse.
"""

from __future__ import annotations
