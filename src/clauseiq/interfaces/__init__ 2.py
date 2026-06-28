"""Interfaces layer — protocol entry points (FastAPI HTTP, MCP).

Thin adapters that translate an external protocol into application use cases.
The FastAPI ``app`` defined here is the single canonical application object;
later milestones attach their ``/api/v1/*`` routes to this same instance.
"""

from __future__ import annotations
