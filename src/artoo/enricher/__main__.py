from __future__ import annotations

import argparse
import asyncio
import logging

from ..catalog.openmetadata import get_default_client
from ..config import settings
from ..logging import configure_logging
from .collector import SchemaCollector
from .enricher import SemanticEnricher
from .writer import CatalogWriter

logger = logging.getLogger(__name__)


async def _process_table(
    fqn: str,
    collector: SchemaCollector,
    enricher: SemanticEnricher,
    writer: CatalogWriter,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        logger.info("Enriching table", extra={"table": fqn})
        context = await collector.collect(fqn)
        enrichment = await enricher.enrich(context)
        await writer.write(fqn, enrichment)
        logger.info("Table enriched", extra={"table": fqn, "columns": len(enrichment.columns)})


async def run_enrichment() -> None:
    configure_logging()
    om_client = await get_default_client()
    await om_client.ensure_governance_taxonomy()
    tables = await om_client.list_tables()
    collector = SchemaCollector(om_client, sample_rows=settings.sample_rows)
    enricher = SemanticEnricher()
    writer = CatalogWriter(om_client)
    semaphore = asyncio.Semaphore(settings.enrichment_concurrency)

    tasks = [_process_table(t.name, collector, enricher, writer, semaphore) for t in tables]
    await asyncio.gather(*tasks)
    await om_client.close()


async def run_bootstrap() -> None:
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "openmetadata" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("openmetadata_bootstrap", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load OpenMetadata bootstrap from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    await mod.main()


def main() -> None:
    parser = argparse.ArgumentParser(description="ARTOO enricher / bootstrap")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Only run OpenMetadata bootstrap (connector + ingestion)",
    )
    args = parser.parse_args()

    if args.bootstrap_only:
        asyncio.run(run_bootstrap())
    else:
        asyncio.run(run_enrichment())


if __name__ == "__main__":
    main()
