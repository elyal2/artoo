from __future__ import annotations

import logging
import math
import re
from typing import Any

from ..config import settings
from ..llm.client import LLMClient
from ..llm.prompts import ENRICHMENT_SYSTEM_PROMPT
from ..models import ColumnMeta, TableContext, TableEnrichment

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """Remove markdown code fences and return clean JSON string."""
    text = text.strip()
    # Full block with closing fence
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Truncated block — no closing fence, grab everything after opening fence
    match = re.search(r"```(?:json)?\s*([\s\S]+)", text)
    if match:
        return match.group(1).strip()
    return text


def _format_context(context: TableContext, note: str | None = None) -> str:
    lines: list[str] = [f"Table: {context.name}"]
    if note:
        lines.append(note)
    if context.row_count:
        lines.append(f"Row count: {context.row_count}")
    lines.append("")
    lines.append("Column analysis (analyze these FIRST to understand the data):")
    lines.append("Columns:")
    for col in context.columns:
        fk = f" FK → {col.foreign_key}" if col.foreign_key else ""
        col_line = f"  - {col.name} ({col.data_type}){fk}"
        if col.description:
            col_line += f" — {col.description}"
        if col.business_name:
            col_line += f" [business_name: {col.business_name}]"
        lines.append(col_line)
    if context.column_stats:
        lines.append("")
        lines.append("Column statistics (use these values to infer business meaning):")
        for col_name, stats in context.column_stats.items():
            distinct = stats.get("distinct_count", "?")
            parts = [f"  - {col_name}: distinct={distinct}"]
            if stats.get("null_pct"):
                parts.append(f"null%={stats['null_pct']}")
            top = stats.get("top_values")
            if top:
                vals = ", ".join(str(t.get("val", "?")) for t in top[:5])
                parts.append(f"top_values=[{vals}]")
                if isinstance(distinct, int) and distinct <= 20:
                    parts.append(
                        "<-- LOW CARDINALITY: document each value with its business meaning"
                    )
            lines.append(" ".join(parts))
    if context.foreign_keys:
        lines.append("")
        lines.append("Foreign keys:")
        for fk in context.foreign_keys:
            lines.append(f"  - {fk}")
    if context.sample_rows:
        lines.append("")
        lines.append("Sample rows (illustrate actual data patterns):")
        for row in context.sample_rows:
            lines.append(f"  - {row}")
    return "\n".join(lines)


def _balanced_batches(columns: list[ColumnMeta], size: int) -> list[list[ColumnMeta]]:
    """Split into the fewest batches of at most `size`, as even as possible."""
    if size <= 0 or len(columns) <= size:
        return [columns]
    count = math.ceil(len(columns) / size)
    base, extra = divmod(len(columns), count)
    batches: list[list[ColumnMeta]] = []
    start = 0
    for i in range(count):
        end = start + base + (1 if i < extra else 0)
        batches.append(columns[start:end])
        start = end
    return batches


def _subset_context(context: TableContext, columns: list[ColumnMeta]) -> TableContext:
    names = {c.name for c in columns}
    return context.model_copy(
        update={
            "columns": columns,
            "column_stats": {k: v for k, v in context.column_stats.items() if k in names},
            "sample_rows": [
                {k: v for k, v in row.items() if k in names} for row in context.sample_rows
            ],
        }
    )


def _batch_note(context: TableContext, columns: list[ColumnMeta], first: bool) -> str | None:
    if len(columns) >= len(context.columns):
        return None
    every = ", ".join(c.name for c in context.columns)
    note = (
        f"This table has {len(context.columns)} columns in total: {every}. "
        "Describe ONLY the columns listed below under 'Columns:'."
    )
    if not first:
        note += (
            ' Table-level fields were produced elsewhere: return "table_description": "", '
            '"business_name": null, "business_domain": null, "suggested_tags": [] and '
            '"common_queries": [].'
        )
    return note


def _merge(left: TableEnrichment, right: TableEnrichment) -> TableEnrichment:
    """Combine two parts of one table; table-level fields come from the first part."""
    return left.model_copy(
        update={
            "table_description": left.table_description or right.table_description,
            "business_name": left.business_name or right.business_name,
            "business_domain": left.business_domain or right.business_domain,
            "columns": {**left.columns, **right.columns},
            "suggested_tags": list(dict.fromkeys(left.suggested_tags + right.suggested_tags)),
            "common_queries": list(dict.fromkeys(left.common_queries + right.common_queries)),
        }
    )


class SemanticEnricher:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient.default()

    async def enrich(self, context: TableContext) -> TableEnrichment:
        batches = _balanced_batches(context.columns, settings.enrichment_column_batch_size)
        if len(batches) > 1:
            logger.info(
                "Wide table %s: %d columns in %d batches",
                context.name,
                len(context.columns),
                len(batches),
            )
        result: TableEnrichment | None = None
        for index, batch in enumerate(batches):
            part = await self._enrich_part(context, batch, first=index == 0)
            result = part if result is None else _merge(result, part)
        assert result is not None  # _balanced_batches always yields at least one batch
        return result

    async def _complete(self, prompt: str) -> str:
        model_kwargs: dict[str, Any] = (
            {"model": settings.enrichment_llm_model} if settings.enrichment_llm_model else {}
        )
        return await self.llm.complete(
            system=ENRICHMENT_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=settings.enrichment_max_tokens,
            **model_kwargs,
        )

    async def _enrich_part(
        self, context: TableContext, columns: list[ColumnMeta], *, first: bool
    ) -> TableEnrichment:
        sub = _subset_context(context, columns)
        response_text = await self._complete(
            _format_context(sub, _batch_note(context, columns, first))
        )
        clean = _strip_markdown(response_text)
        try:
            return TableEnrichment.model_validate_json(clean)
        except Exception:
            if len(columns) > 1:
                # Truncated or malformed JSON: retry each half instead of losing every column.
                logger.warning(
                    "Truncated/invalid JSON for %s (%d columns) — splitting the batch",
                    context.name,
                    len(columns),
                )
                mid = len(columns) // 2
                left = await self._enrich_part(context, columns[:mid], first=first)
                right = await self._enrich_part(context, columns[mid:], first=False)
                return _merge(left, right)
            logger.warning(
                "Truncated/invalid JSON for %s — using partial description", context.name
            )
            return self._partial(clean, table_level=first)

    @staticmethod
    def _partial(clean: str, *, table_level: bool) -> TableEnrichment:
        """Best-effort result from unparseable JSON: keep only what a regex can recover."""
        desc_match = re.search(r'"table_description"\s*:\s*"([^"]+)"', clean)
        domain_match = re.search(r'"business_domain"\s*:\s*"([^"]+)"', clean)
        desc = desc_match.group(1) if desc_match else clean[:200].replace("```json", "").strip()
        return TableEnrichment(
            table_description=desc if table_level else "",
            business_domain=domain_match.group(1) if table_level and domain_match else None,
            columns={},
        )


__all__ = ["SemanticEnricher"]
