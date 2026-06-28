"""Show a human-readable diff between the committed corpus and a fresh fetch.

Volatile fields (``version``, ``source_fetched_at``) are normalised out so the
diff highlights *substantive* changes (section text/titles/count), which is what
a reviewer should inspect before committing a refreshed corpus.

Exit code is 1 when there are substantive differences (handy in CI), 0 otherwise.

Usage:
    uv run python scripts/diff_law_corpus.py [--local PATH] [--url URL]
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from datetime import date
from pathlib import Path

from clauseiq.config import settings
from clauseiq.infrastructure.ingestion.law_ingestor import (
    ICA_SOURCE_URL,
    LawCorpus,
    fetch_corpus_from_source,
    load_corpus,
)

_PLACEHOLDER_DATE = date(1900, 1, 1)


def _normalise(corpus: LawCorpus) -> list[str]:
    """Render a corpus to JSON lines with volatile fields blanked out."""
    snapshot = corpus.model_copy(deep=True)
    snapshot.version = "<version>"
    snapshot.source_fetched_at = _PLACEHOLDER_DATE
    for section in snapshot.sections:
        section.version = "<version>"
        section.source_fetched_at = _PLACEHOLDER_DATE
    return snapshot.model_dump_json(indent=2).splitlines(keepends=True)


async def _run(local_path: Path, url: str) -> int:
    local = _normalise(load_corpus(local_path))
    fresh = _normalise(await fetch_corpus_from_source(url, fetched_at=date.today()))
    diff = list(difflib.unified_diff(local, fresh, fromfile="committed", tofile="fresh", n=2))
    if not diff:
        print("No substantive differences (volatile fields ignored).")
        return 0
    sys.stdout.writelines(diff)
    print(f"\n{sum(1 for line in diff if line.startswith(('+', '-')))} changed lines.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff committed law corpus vs a fresh fetch.")
    parser.add_argument("--local", type=Path, default=settings.law_corpus_path)
    parser.add_argument("--url", default=ICA_SOURCE_URL)
    args = parser.parse_args()
    return asyncio.run(_run(args.local, args.url))


if __name__ == "__main__":
    raise SystemExit(main())
