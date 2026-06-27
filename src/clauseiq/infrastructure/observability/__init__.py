"""Observability — token/cost accounting and Langfuse tracing.

``usage`` accumulates token counts and computes ``cost_usd`` per the model
pricing table; ``langfuse_client`` provides the ``@traced`` decorator that
records ``trace_id``, ``agent_name``, ``latency_ms``, ``tokens_used`` and
``cost_usd`` for every agent node and tool call (to structlog always, and to
Langfuse when configured).
"""

from __future__ import annotations
