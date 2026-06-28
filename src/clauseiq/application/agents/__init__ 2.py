"""LangGraph agents: the multi-agent analysis pipeline.

A supervisor (Gemini Flash) segments the contract and plans retrieval, a
retriever fetches relevant law, a risk analyzer (Gemini Pro) scores clauses, and
a citation verifier validates every proposed citation against the corpus. Each
agent is a node in the LangGraph ``StateGraph`` assembled in
:mod:`clauseiq.application.workflows`.
"""

from __future__ import annotations
