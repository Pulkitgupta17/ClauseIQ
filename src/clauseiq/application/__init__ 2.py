"""Application layer — orchestration and use cases.

Coordinates the domain and the ports (via the LangGraph multi-agent pipeline and
the ``analyze_contract`` use case). Depends only on the domain; the concrete
adapters are injected by the interfaces layer.
"""

from __future__ import annotations
