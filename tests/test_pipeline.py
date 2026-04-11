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
    async def complete(self, *, system, user):  # noqa: ANN001
        if "SELECT" in user or "Schema" in user:
            return json.dumps(
                {
                    "sql": "SELECT 1 as value",
                    "tables_used": ["bkng"],
                    "confidence": "high",
                    "reasoning": "demo",
                }
            )
        return "Result is static"


class FakeConn:
    async def fetch(self, sql):  # noqa: ANN001
        return [SimpleNamespace(value=1).__dict__]


class FakePool:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def acquire(self):
        return FakeConn()


@pytest.mark.asyncio
async def test_pipeline_executes_query(monkeypatch):
    table = TableDetail(
        name="bkng",
        description="Bookings",
        business_domain="booking",
        columns=[ColumnMeta(name="value", data_type="int")],
        foreign_keys=[],
    )
    catalog = FakeCatalog(table)
    pipeline = QueryPipeline(catalog, llm=FakeLLM())

    async def fake_pool_get():
        return FakePool()

    monkeypatch.setattr(pipeline, "_pool_get", fake_pool_get)

    response = await pipeline.query("What is value?")
    assert response.sql.lower().startswith("select")
    assert response.rows[0]["value"] == 1
