from __future__ import annotations

import json
import logging
import re

from ..llm.client import LLMClient
from ..llm.prompts import ENRICHMENT_SYSTEM_PROMPT
from ..models import TableContext, TableEnrichment

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
            distinct = stats.get("distinct_count", "?")
            parts = [f"  - {col_name}: distinct={distinct}"]
            if stats.get("null_pct"):
                parts.append(f"null%={stats['null_pct']}")
            top = stats.get("top_values")
            if top:
                vals = ", ".join(str(t.get("val", "?")) for t in top[:5])
                parts.append(f"top_values=[{vals}]")
                # Explicitly flag low-cardinality columns for the LLM
                if isinstance(distinct, int) and distinct <= 20:
                    parts.append(
                        f"<-- LOW CARDINALITY: document each value with its business meaning inferred from column name '{col_name}' and table context"
                    )
            lines.append(" ".join(parts))
    lines.append(f"Row count: {context.row_count}")
    return "\n".join(lines)


class SemanticEnricher:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient.default()

    async def enrich(self, context: TableContext) -> TableEnrichment:
        prompt = _format_context(context)
        response_text = await self.llm.complete(system=ENRICHMENT_SYSTEM_PROMPT, user=prompt)
        clean = _strip_markdown(response_text)
        try:
            return TableEnrichment.model_validate_json(clean)
        except Exception:
            # Try to extract table_description from truncated JSON
            desc_match = re.search(r'"table_description"\s*:\s*"([^"]+)"', clean)
            domain_match = re.search(r'"business_domain"\s*:\s*"([^"]+)"', clean)
            desc = desc_match.group(1) if desc_match else clean[:200].replace("```json", "").strip()
            logger.warning(
                "Truncated/invalid JSON for %s — using partial description", context.name
            )
            wrapped = {
                "table_description": desc,
                "business_domain": domain_match.group(1) if domain_match else None,
                "columns": {},
                "suggested_tags": [],
                "common_queries": [],
            }
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
