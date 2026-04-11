from __future__ import annotations

import logging

from ..catalog.openmetadata import OpenMetadataClient
from ..models import TableEnrichment

logger = logging.getLogger(__name__)


class CatalogWriter:
    def __init__(self, om_client: OpenMetadataClient) -> None:
        self.om = om_client

    async def write(self, table_fqn: str, enrichment: TableEnrichment) -> None:
        # Build a single patch with table description + all column patches
        ops: list[dict] = [
            {"op": "add", "path": "/description", "value": enrichment.table_description},
        ]

        # Get column indices once if we have column enrichments
        col_indices: dict[str, int] = {}
        if enrichment.columns:
            try:
                col_indices = await self.om.get_column_indices(table_fqn)
            except Exception as exc:
                logger.warning("Could not get column indices for %s: %s", table_fqn, exc)

        # Build column patch ops using index-based paths
        pii_count = 0
        for col_name, col_info in enrichment.columns.items():
            idx = col_indices.get(col_name)
            if idx is None:
                continue
            if col_info.description:
                ops.append(
                    {
                        "op": "add",
                        "path": f"/columns/{idx}/description",
                        "value": col_info.description,
                    }
                )
            if col_info.business_name:
                ops.append(
                    {
                        "op": "add",
                        "path": f"/columns/{idx}/displayName",
                        "value": col_info.business_name,
                    }
                )
            if col_info.pii and col_info.pii_type:
                ops.append(
                    {
                        "op": "add",
                        "path": f"/columns/{idx}/tags/-",
                        "value": {"tagFQN": f"PII.Sensitive"},
                    }
                )
                pii_count += 1

        # Send single PATCH for table + columns — try FQN first, fallback to ID
        try:
            await self.om.patch_table(table_fqn, ops)
            logger.info("Updated table description for %s", table_fqn)
        except Exception:
            # Fallback: patch by ID (handles corrupted FQN index)
            try:
                table_id = await self.om.get_table_id(table_fqn)
                await self.om.patch_table_by_id(table_id, ops)
                logger.info("Updated table description for %s (via ID fallback)", table_fqn)
            except Exception as exc2:
                logger.warning("Could not patch %s: %s", table_fqn, exc2)
                return

        # Apply tags separately (best-effort)
        if enrichment.suggested_tags:
            try:
                tag_fqns = [f"Business.{t}" for t in enrichment.suggested_tags]
                await self.om.put_table_tags(table_fqn, tag_fqns)
                logger.info("Applied %d business tags to %s", len(tag_fqns), table_fqn)
            except Exception as exc:
                logger.warning("Could not apply tags to %s: %s", table_fqn, exc)

        logger.info(
            "Enriched %s — %d columns, %d PII",
            table_fqn,
            len(enrichment.columns),
            pii_count,
        )


__all__ = ["CatalogWriter"]
