from __future__ import annotations

import logging

from ..catalog.openmetadata import OpenMetadataClient
from ..models import TableEnrichment

logger = logging.getLogger(__name__)


class CatalogWriter:
    def __init__(self, om_client: OpenMetadataClient) -> None:
        self.om = om_client

    async def write(self, table_fqn: str, enrichment: TableEnrichment) -> None:
        table_patch = [
            {"op": "replace", "path": "/description", "value": enrichment.table_description},
        ]
        await self.om.patch_table(table_fqn, table_patch)
        logger.info("Updated table description for %s", table_fqn)

        if enrichment.suggested_tags:
            tag_fqns = [f"Business.{t}" for t in enrichment.suggested_tags]
            await self.om.put_table_tags(table_fqn, tag_fqns)
            logger.info("Applied %d business tags to %s", len(tag_fqns), table_fqn)

        for col_name, col_info in enrichment.columns.items():
            column_patch = [
                {"op": "replace", "path": "/description", "value": col_info.description},
                {"op": "replace", "path": "/displayName", "value": col_info.business_name},
            ]
            if col_info.pii and col_info.pii_type:
                column_patch.append(
                    {
                        "op": "add",
                        "path": "/tags/-",
                        "value": {"tagFQN": f"PII.{col_info.pii_type}"},
                    }
                )
            await self.om.patch_column(table_fqn, col_name, column_patch)

        logger.info(
            "Enriched %s — %d columns, %d PII",
            table_fqn,
            len(enrichment.columns),
            sum(1 for c in enrichment.columns.values() if c.pii),
        )


__all__ = ["CatalogWriter"]
