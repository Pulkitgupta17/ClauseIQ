"""LLM adapters.

The ``LLMClient`` port abstracts text and structured generation; ``GeminiClient``
(and its Flash/Pro subclasses) implement it over Google's free-tier Gemini via
the ``google-genai`` SDK. The ``factory`` selects a client by role
(orchestration vs analysis). All calls are async and return ``Result`` values.
"""

from __future__ import annotations
