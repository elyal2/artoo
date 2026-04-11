from __future__ import annotations

from typing import Any, Dict, List

import asyncpg

from ..catalog.openmetadata import OpenMetadataClient
from ..config import settings
from ..models import ColumnMeta, TableContext


def _pg_dsn_for_asyncpg(raw_dsn: str) -> str:
    dsn = raw_dsn.replace("+psycopg2", "")
    if "postgres:5432" in dsn and "postgresql:5432" not in dsn:
        dsn = dsn.replace("postgres:5432", "postgresql:5432")
    return dsn


class SchemaCollector:
    def __init__(self, om_client: OpenMetadataClient, sample_rows: int = 5) -> None:
        self.om = om_client
        self.sample_rows = sample_rows
        self.pg_dsn = _pg_dsn_for_asyncpg(settings.postgres_dsn)

    async def collect(self, table_fqn: str) -> TableContext:
        table = await self.om.get_table(table_fqn)
        table_name = table.name.split(".")[-1]
        async with asyncpg.create_pool(self.pg_dsn, min_size=1, max_size=2) as pool:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT {self.sample_rows}"
                )
                row_count: int = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                stats = await self._compute_column_stats(conn, table_name, table.columns)

        sample_rows_list = [dict(r) for r in rows]
        columns: List[ColumnMeta] = list(table.columns)
        return TableContext(
            name=table.name,
            columns=columns,
            sample_rows=sample_rows_list,
            foreign_keys=table.foreign_keys,
            column_stats=stats,
            row_count=row_count,
        )

    async def _compute_column_stats(
        self,
        conn: asyncpg.Connection,
        table_name: str,
        columns: List[ColumnMeta],
    ) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for col in columns:
            try:
                dist_count = await conn.fetchval(
                    f'SELECT COUNT(DISTINCT "{col.name}") FROM {table_name}'
                )
                null_pct = await conn.fetchval(
                    f'SELECT CASE WHEN COUNT(*) = 0 THEN 0 ELSE ROUND(100.0 * SUM(CASE WHEN "{col.name}" IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) END FROM {table_name}'
                )
                top_values = await conn.fetch(
                    f'SELECT "{col.name}" AS val, COUNT(*) AS cnt FROM {table_name} WHERE "{col.name}" IS NOT NULL GROUP BY "{col.name}" ORDER BY cnt DESC LIMIT 5'
                )
                stats[col.name] = {
                    "distinct_count": dist_count,
                    "null_pct": float(null_pct or 0),
                    "top_values": [dict(r) for r in top_values],
                }
            except Exception:
                stats[col.name] = {"distinct_count": 0, "null_pct": 0.0, "top_values": []}
        return stats


__all__ = ["SchemaCollector"]
