"""Evaluation harness — golden dataset, metrics, and a pytest-compatible runner.

This is the quality layer: a curated dataset of contracts with expected findings,
DeepEval metrics (faithfulness, relevancy, context recall/precision) plus custom
metrics (deterministic citation accuracy, LLM-judged legal soundness), and a
runner that scores the live pipeline against the dataset.
"""

from __future__ import annotations
