"""Guardrails — cheap, deterministic safety checks around the LLM pipeline.

* ``input_filter``        — reject inputs that aren't contracts (e.g. a recipe).
* ``injection_detector``  — flag prompt-injection attempts hidden in the text.
* ``output_filter``       — guarantee the legal disclaimer is attached to output.

All three are pure, dependency-light functions so they run before/after the
expensive model calls and are trivially unit-testable.
"""

from __future__ import annotations
