"""ClauseIQ — multi-agent AI for Indian contract analysis.

Top-level package. Layering follows clean/hexagonal architecture:

* :mod:`clauseiq.domain`        — pure business types (no third-party deps).
* :mod:`clauseiq.application`   — orchestration / use cases.
* :mod:`clauseiq.infrastructure`— adapters for the outside world.
* :mod:`clauseiq.interfaces`    — protocol entry points (FastAPI, MCP).

The dependency rule is strict: inner layers never import outer layers.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
