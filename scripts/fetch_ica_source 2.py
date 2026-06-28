"""Fetch the official Indian Contract Act PDF and (re)build the corpus JSON.

This is the *refresh* tool for the committed source-of-truth corpus
(``data/laws/indian_contract_act_1872.json``). Run it, review the diff with
``scripts/diff_law_corpus.py``, then commit the updated JSON.

Usage:
    uv run python scripts/fetch_ica_source.py [--url URL] [--output PATH]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from clauseiq.config import settings
from clauseiq.infrastructure.ingestion.law_ingestor import (
    ICA_SOURCE_URL,
    fetch_corpus_from_source,
)
from clauseiq.logging_config import configure_logging, get_logger

log = get_logger(__name__)


async def _run(url: str, output: Path) -> int:
    corpus = await fetch_corpus_from_source(url, fetched_at=date.today())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(corpus.model_dump_json(indent=2) + "\n", encoding="utf-8")
    log.info(
        "corpus_written",
        path=str(output),
        sections=len(corpus.sections),
        version=corpus.version,
    )
    print(f"Wrote {len(corpus.sections)} sections to {output} (version {corpus.version}).")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Fetch and build the ICA law corpus JSON.")
    parser.add_argument("--url", default=ICA_SOURCE_URL, help="Source PDF URL.")
    parser.add_argument(
        "--output",
        type=Path,
        default=settings.law_corpus_path,
        help="Destination JSON path.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.url, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
