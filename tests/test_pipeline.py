import json
from types import SimpleNamespace

import pytest

from artoo.api.pipeline import QueryPipeline
from artoo.catalog.openmetadata import OpenMetadataClient
from artoo.models import ColumnMeta, TableDetail


class FakeCatalog(OpenMetadataClient):  # type: ignore[misc]
    def __init__(self, table: TableDetail):
        self.table = table

    async def semantic_search(self, query: str, n_results: int = 5):  # noqa: ARG002
        return [self.table]

    async def list_tables(self):
        return []

    async def get_table(self, fqn: str):
        return self.table

    async def close(self):
        return None


class FakeLLM:
    async def complete(self, *, system, user, model=None, max_tokens=None):  # noqa: ANN001
        if "SELECT" in user or "Schema" in user:
            return json.dumps(
                {
                    "sql": "SELECT 1 as value",
                    "tables_used": ["orders"],
                    "confidence": "high",
                    "reasoning": "demo",
                }
            )
        if "chart" in (system or "").lower() or "d3" in (system or "").lower():
            return json.dumps(
                {
                    "chart_type": "none",
                    "analysis": "Single row, no visualization possible.",
                    "d3_code": None,
                }
            )
        return "Result is static"


class FakeCatalogWithTemporal(OpenMetadataClient):  # type: ignore[misc]
    def __init__(self, table: TableDetail):
        self.table = table

    async def semantic_search(self, query: str, n_results: int = 5):  # noqa: ARG002
        return [self.table]

    async def list_tables(self):
        return []

    async def get_table(self, fqn: str):
        return self.table

    async def close(self):
        return None


class FakeConn:
    async def execute(self, sql, **kwargs):  # noqa: ANN001  # EXPLAIN dry-run
        return None

    async def fetch(self, sql, **kwargs):  # noqa: ANN001
        return [SimpleNamespace(value=1).__dict__]


class FakeAcquire:
    async def __aenter__(self):
        return FakeConn()

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False


class FakePool:
    def acquire(self):  # noqa: ANN201
        return FakeAcquire()


@pytest.mark.asyncio
async def test_pipeline_executes_query(monkeypatch):
    table = TableDetail(
        name="orders",
        description="Orders",
        business_domain="sales",
        columns=[ColumnMeta(name="value", data_type="int")],
        foreign_keys=[],
    )
    catalog = FakeCatalog(table)
    pipeline = QueryPipeline(catalog, llm=FakeLLM())

    fake_pool = FakePool()
    monkeypatch.setattr(pipeline, "_pool", fake_pool)

    response = await pipeline.query("What is value?")
    assert response.sql.lower().startswith("select")
    assert response.rows[0]["value"] == 1


@pytest.mark.asyncio
async def test_pipeline_rejects_unknown_columns(monkeypatch):
    """Validator catches qualified column refs that don't exist in the resolved table."""
    table = TableDetail(
        name="revenue",
        description="Revenue",
        business_domain="sales",
        columns=[ColumnMeta(name="created_at", data_type="date")],
        foreign_keys=[],
    )
    catalog = FakeCatalogWithTemporal(table)
    pipeline = QueryPipeline(catalog, llm=FakeLLM())
    monkeypatch.setattr(pipeline, "_pool", FakePool())

    async def fake_complete(*, system, user, model=None, max_tokens=None):  # noqa: ANN001
        # Uses alias r. — 'amount' does not exist on table 'revenue'
        return json.dumps(
            {
                "sql": "SELECT r.created_at, SUM(r.amount) FROM revenue r GROUP BY r.created_at",
                "tables_used": ["revenue"],
                "confidence": "high",
            }
        )

    pipeline.llm.complete = fake_complete  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="does not exist"):
        await pipeline.query("growth of revenue")
