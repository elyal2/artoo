from __future__ import annotations

import json

from ..llm.client import LLMClient
from ..llm.prompts import ENRICHMENT_SYSTEM_PROMPT
from ..models import TableContext, TableEnrichment


def _format_context(context: TableContext) -> str:
    lines: list[str] = [f"Table: {context.name}"]
    lines.append("Columns:")
    for col in context.columns:
        fk = f" FK {col.foreign_key}" if col.foreign_key else ""
        lines.append(f"  - {col.name} ({col.data_type}){fk}")
    if context.foreign_keys:
        lines.append("Foreign keys:")
        for fk in context.foreign_keys:
            lines.append(f"  - {fk}")
    if context.sample_rows:
        lines.append("Sample rows:")
        for row in context.sample_rows:
            lines.append(f"  - {row}")
    if context.column_stats:
        lines.append("Column statistics:")
        for col_name, stats in context.column_stats.items():
            parts = [f"  - {col_name}: distinct={stats.get('distinct_count', '?')}"]
            if stats.get("null_pct"):
                parts.append(f"null%={stats['null_pct']}")
            top = stats.get("top_values")
            if top:
                vals = ", ".join(str(t.get("val", "?")) for t in top[:5])
                parts.append(f"top=[{vals}]")
            lines.append(" ".join(parts))
    lines.append(f"Row count: {context.row_count}")
    return "\n".join(lines)


class SemanticEnricher:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient.default()

    async def enrich(self, context: TableContext) -> TableEnrichment:
        prompt = _format_context(context)
        response_text = await self.llm.complete(system=ENRICHMENT_SYSTEM_PROMPT, user=prompt)
        try:
            return TableEnrichment.model_validate_json(response_text)
        except Exception:
            wrapped = self._wrap_response(response_text)
            return TableEnrichment.model_validate_json(json.dumps(wrapped))

    @staticmethod
    def _wrap_response(text: str) -> dict[str, object]:
        return {
            "table_description": text[:200],
            "business_domain": None,
            "columns": {},
            "suggested_tags": [],
            "common_queries": [],
        }


__all__ = ["SemanticEnricher"]
