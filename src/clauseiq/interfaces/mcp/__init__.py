"""MCP interface — exposes ClauseIQ's use cases as tools for Claude Desktop.

In MCP mode Claude is the supervisor: it decides when to call ``analyze_contract``,
``search_indian_law``, or ``verify_citation``. Each tool wraps the same
application use cases the HTTP API uses; internal sub-tasks still run on free
Gemini. Transport is stdio (see :mod:`clauseiq.interfaces.mcp.server`).
"""

from __future__ import annotations
