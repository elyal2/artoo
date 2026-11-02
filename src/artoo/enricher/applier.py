"""Write the accepted items of a proposal to OpenMetadata."""

from __future__ import annotations

import logging
from collections import defaultdict

from ..catalog.openmetadata import BUSINESS_RULES_PROPERTY, OpenMetadataClient
from ..models import TableDetail
from .proposal import (
    COLUMN_FIELDS,
    ApplyOutcome,
    ApplyResult,
    ProposalItem,
    current_value,
)

logger = logging.getLogger(__name__)

_COLUMN_PATH = {"column_description": "description", "column_display_name": "displayName"}


def _same(a: str | None, b: str | None) -> bool:
    return (a or "").strip() == (b or "").strip()


class ProposalApplier:
    def __init__(self, catalog: OpenMetadataClient) -> None:
        self.catalog = catalog

    async def apply(self, items: list[ProposalItem]) -> ApplyResult:
        by_table: dict[str, list[ProposalItem]] = defaultdict(list)
        for item in items:
            by_table[item.table].append(item)

        outcomes: list[ApplyOutcome] = []
        for table_fqn, table_items in by_table.items():
            try:
                table = await self.catalog.get_table(table_fqn)
                indices = (
                    await self.catalog.get_column_indices(table_fqn)
                    if any(i.field in COLUMN_FIELDS for i in table_items)
                    else {}
                )
            except Exception as exc:
                logger.warning("Cannot read %s: %s", table_fqn, exc)
                outcomes.extend(
                    ApplyOutcome(id=i.id, status="error", detail=f"Cannot read table: {exc}")
                    for i in table_items
                )
                continue
            for item in table_items:
                outcomes.append(await self._apply_one(table, indices, item))
        order = {i.id: n for n, i in enumerate(items)}
        outcomes.sort(key=lambda o: order[o.id])
        return ApplyResult(outcomes=outcomes)

    async def _apply_one(
        self, table: TableDetail, indices: dict[str, int], item: ProposalItem
    ) -> ApplyOutcome:
        after = item.after.strip()
        if not after:
            return ApplyOutcome(id=item.id, status="error", detail="Empty value")
        # Optimistic check: someone may have edited the catalog since the proposal was made.
        now = current_value(table, item.column, item.field)
        if not _same(now, item.before):
            return ApplyOutcome(
                id=item.id,
                status="error",
                detail="Changed in the catalog since this proposal was made; propose again.",
            )
        try:
            if item.field == "table_description":
                await self.catalog.patch_table(
                    item.table, [{"op": "add", "path": "/description", "value": after}]
                )
            elif item.field == "table_display_name":
                await self.catalog.patch_table(
                    item.table, [{"op": "add", "path": "/displayName", "value": after}]
                )
            elif item.field == "table_business_rules":
                await self.catalog.merge_table_extension(
                    item.table, {BUSINESS_RULES_PROPERTY: after}
                )
            else:
                idx = indices.get(item.column or "")
                if idx is None:
                    return ApplyOutcome(
                        id=item.id, status="error", detail=f"Unknown column {item.column}"
                    )
                await self.catalog.patch_table(
                    item.table,
                    [
                        {
                            "op": "add",
                            "path": f"/columns/{idx}/{_COLUMN_PATH[item.field]}",
                            "value": after,
                        }
                    ],
                )
        except Exception as exc:
            logger.warning("Could not apply %s on %s: %s", item.field, item.table, exc)
            return ApplyOutcome(id=item.id, status="error", detail=str(exc))
        return ApplyOutcome(id=item.id, status="ok")
