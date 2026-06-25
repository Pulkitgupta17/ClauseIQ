"""Bootstrap the committed law corpus into ChromaDB.

Loads ``data/laws/indian_contract_act_1872.json``, chunks + embeds each section,
and upserts into the configured ChromaDB collection. Idempotent: re-running
upserts by stable chunk id, so it will not create duplicates.

Usage:
    uv run python scripts/ingest_laws.py [--corpus PATH]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from clauseiq.config import settings
from clauseiq.infrastructure.ingestion.law_ingestor import run_ingestion
from clauseiq.logging_config import configure_logging, get_logger

log = get_logger(__name__)


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Ingest the law corpus into ChromaDB.")
    parser.add_argument("--corpus", type=Path, default=settings.law_corpus_path)
    args = parser.parse_args()

    report = asyncio.run(run_ingestion(corpus_path=args.corpus))
    log.info("ingest_done", sections=report.sections, chunks=report.chunks)
    print(
        f"Ingested {report.sections} sections "
        f"({report.chunks} chunks) into collection '{settings.chroma_collection_law}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
