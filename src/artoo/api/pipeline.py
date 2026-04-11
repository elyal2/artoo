from __future__ import annotations

import json

import asyncpg

from ..catalog.openmetadata import OpenMetadataClient
from ..config import settings
from ..llm.client import LLMClient
from ..llm.prompts import QUERY_SYSTEM_PROMPT
from ..models import QueryResponse, SQLResponse, TableDetail
from .validator import validate_sql


class QueryPipeline:
    def __init__(self, catalog: OpenMetadataClient, llm: LLMClient | None = None) -> None:
        self.catalog = catalog
        self.llm = llm or LLMClient.default()
        self._pool: asyncpg.Pool | None = None
        self._dsn = _pg_dsn(settings.postgres_dsn)

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    async def _schema_context(self, tables: list[TableDetail]) -> str:
        parts: list[str] = []
        for table in tables:
            lines = [f"TABLE: {table.name} — {table.description or ''}"]
            if table.business_domain:
                lines.append(f"Business domain: {table.business_domain}")
            lines.append("COLUMNS:")
            for col in table.columns:
                line = f"  - {col.name} ({col.data_type})"
                if col.business_name:
                    line += f" — {col.business_name}"
                if col.description:
                    line += f": {col.description}"
                if col.example_values:
                    line += f" [examples: {col.example_values}]"
                lines.append(line)
            if table.foreign_keys:
                lines.append("RELATIONSHIPS:")
                for fk in table.foreign_keys:
                    lines.append(f"  - {fk}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    async def query(self, question: str) -> QueryResponse:
        tables = await self.catalog.semantic_search(question, n_results=5)
        context = await self._schema_context(tables)

        sql_candidate = await self.llm.complete(
            system=QUERY_SYSTEM_PROMPT,
            user=f"Question: {question}\nSchema:\n{context}",
        )
        parsed = SQLResponse.model_validate_json(sql_candidate)
        sql = validate_sql(parsed.sql)

        pool = await self._ensure_pool()
        timeout = settings.query_timeout_seconds
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, timeout=timeout)
        rows_dict = [dict(r) for r in rows[: settings.max_result_rows]]

        explanation = await self.llm.complete(
            system="Explain the SQL result briefly for a business audience.",
            user=json.dumps({"question": question, "sql": sql, "sample": rows_dict[:5]}),
        )

        return QueryResponse(
            question=question,
            sql=sql,
            explanation=explanation,
            rows=rows_dict,
            tables_used=parsed.tables_used,
            confidence=parsed.confidence,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()


def _pg_dsn(raw_dsn: str) -> str:
    dsn = raw_dsn.replace("+psycopg2", "")
    if "postgres:5432" in dsn and "postgresql:5432" not in dsn:
        dsn = dsn.replace("postgres:5432", "postgresql:5432")
    return dsn


__all__ = ["QueryPipeline"]
