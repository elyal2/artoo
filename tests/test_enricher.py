import json

import pytest

from artoo.enricher.enricher import SemanticEnricher
from artoo.models import ColumnMeta, TableContext


class FakeLLM:
    async def complete(self, *, system, user):  # noqa: ANN001
        return json.dumps(
            {
                "table_description": "Bookings table",
                "business_domain": "booking",
                "columns": {
                    "id": {
                        "description": "Booking id",
                        "business_name": "Booking ID",
                        "pii": False,
                        "pii_type": None,
                        "sensitivity": "internal",
                        "example_values": "1",
                    }
                },
                "suggested_tags": ["booking"],
                "common_queries": ["How many bookings?"],
            }
        )


@pytest.mark.asyncio
async def test_enricher_parses_llm_json():
    enricher = SemanticEnricher(llm_client=FakeLLM())
    ctx = TableContext(name="bkng", columns=[ColumnMeta(name="id", data_type="int")])
    result = await enricher.enrich(ctx)
    assert result.table_description == "Bookings table"
    assert "id" in result.columns
