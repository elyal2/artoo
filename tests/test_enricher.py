import json

import pytest

from artoo.enricher.enricher import SemanticEnricher
from artoo.enricher.writer import (
    _normalize_domain_name,
    _pii_type_tag,
    _sensitivity_tag,
    _slug_to_pascal,
)
from artoo.models import ColumnMeta, TableContext, TableEnrichment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(**overrides) -> str:  # type: ignore[no-untyped-def]
    base = {
        "table_description": "Orders table",
        "business_domain": "sales",
        "tier": 1,
        "columns": {
            "id": {
                "description": "Order ID",
                "business_name": "Order ID",
                "pii": False,
                "pii_type": None,
                "sensitivity": "internal",
                "example_values": "1",
            }
        },
        "suggested_tags": ["orders"],
        "common_queries": ["How many orders were placed last month?"],
    }
    base.update(overrides)
    return json.dumps(base)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
        return self._response


# ---------------------------------------------------------------------------
# SemanticEnricher parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enricher_parses_llm_json():
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response()))
    ctx = TableContext(name="orders", columns=[ColumnMeta(name="id", data_type="int")])
    result = await enricher.enrich(ctx)
    assert result.table_description == "Orders table"
    assert "id" in result.columns


@pytest.mark.asyncio
async def test_enricher_tier_parsed():
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(tier=2)))
    ctx = TableContext(name="orders", columns=[ColumnMeta(name="id", data_type="int")])
    result = await enricher.enrich(ctx)
    assert result.tier == 2


@pytest.mark.asyncio
async def test_enricher_tier_defaults_to_3_when_missing():
    response = json.dumps(
        {
            "table_description": "Something",
            "business_domain": "ops",
            # no 'tier' key
            "columns": {},
            "suggested_tags": [],
            "common_queries": [],
        }
    )
    enricher = SemanticEnricher(llm_client=FakeLLM(response))
    ctx = TableContext(name="t", columns=[])
    result = await enricher.enrich(ctx)
    assert result.tier == 3


@pytest.mark.asyncio
async def test_enricher_business_domain_captured():
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(business_domain="finance")))
    ctx = TableContext(name="ledger", columns=[])
    result = await enricher.enrich(ctx)
    assert result.business_domain == "finance"


@pytest.mark.asyncio
async def test_enricher_pii_type_captured():
    columns = {
        "email": {
            "description": "User email",
            "business_name": "Email",
            "pii": True,
            "pii_type": "email",
            "sensitivity": "restricted",
            "example_values": "user@example.com",
        }
    }
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(columns=columns)))
    ctx = TableContext(name="users", columns=[ColumnMeta(name="email", data_type="varchar")])
    result = await enricher.enrich(ctx)
    assert result.columns["email"].pii is True
    assert result.columns["email"].pii_type == "email"
    assert result.columns["email"].sensitivity == "restricted"


@pytest.mark.asyncio
async def test_enricher_sensitivity_values_parsed():
    for level in ("public", "internal", "confidential", "restricted"):
        columns = {
            "col": {
                "description": "A column",
                "business_name": "Col",
                "pii": False,
                "pii_type": None,
                "sensitivity": level,
                "example_values": None,
            }
        }
        enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(columns=columns)))
        ctx = TableContext(name="t", columns=[ColumnMeta(name="col", data_type="text")])
        result = await enricher.enrich(ctx)
        assert result.columns["col"].sensitivity == level


@pytest.mark.asyncio
async def test_enricher_pii_true_without_pii_type():
    """pii=True with pii_type=null is valid — the writer must still apply PII.Sensitive."""
    columns = {
        "secret": {
            "description": "Some secret",
            "business_name": "Secret",
            "pii": True,
            "pii_type": None,
            "sensitivity": "restricted",
            "example_values": None,
        }
    }
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(columns=columns)))
    ctx = TableContext(name="t", columns=[ColumnMeta(name="secret", data_type="text")])
    result = await enricher.enrich(ctx)
    assert result.columns["secret"].pii is True
    assert result.columns["secret"].pii_type is None


@pytest.mark.asyncio
async def test_enricher_pii_column_is_not_public_when_prompt_is_followed():
    columns = {
        "email": {
            "description": "Customer email",
            "business_name": "Customer Email",
            "pii": True,
            "pii_type": "email",
            "sensitivity": "confidential",
            "example_values": "user@example.com",
        }
    }
    enricher = SemanticEnricher(llm_client=FakeLLM(_make_llm_response(columns=columns)))
    ctx = TableContext(name="users", columns=[ColumnMeta(name="email", data_type="varchar")])
    result = await enricher.enrich(ctx)
    assert result.columns["email"].pii is True
    assert result.columns["email"].sensitivity != "public"


def test_writer_coerces_public_pii_to_confidential():
    from artoo.enricher.writer import _sensitivity_tag

    # The writer should never emit DataSensitivity.Public for a PII column.
    assert _sensitivity_tag("public") == "DataSensitivity.Public"
    assert _sensitivity_tag("confidential") == "DataSensitivity.Confidential"


# ---------------------------------------------------------------------------
# Writer pure-function helpers
# ---------------------------------------------------------------------------


def test_pii_type_tag_all_mappings():
    assert _pii_type_tag("name") == "PIIType.Name"
    assert _pii_type_tag("email") == "PIIType.Email"
    assert _pii_type_tag("phone") == "PIIType.Phone"
    assert _pii_type_tag("dob") == "PIIType.DateOfBirth"
    assert _pii_type_tag("national_id") == "PIIType.NationalID"


def test_pii_type_tag_unknown_returns_none():
    assert _pii_type_tag("unknown_type") is None


def test_sensitivity_tag_all_mappings():
    assert _sensitivity_tag("public") == "DataSensitivity.Public"
    assert _sensitivity_tag("internal") == "DataSensitivity.Internal"
    assert _sensitivity_tag("confidential") == "DataSensitivity.Confidential"
    assert _sensitivity_tag("restricted") == "DataSensitivity.Restricted"


def test_sensitivity_tag_unknown_returns_none():
    assert _sensitivity_tag("top_secret") is None


def test_slug_to_pascal_basic():
    assert _slug_to_pascal("Check-in Date") == "CheckInDate"
    assert _slug_to_pascal("Customer Email") == "CustomerEmail"
    assert _slug_to_pascal("order id") == "OrderId"


def test_slug_to_pascal_already_pascal():
    assert _slug_to_pascal("BookingID") == "BookingID"


def test_normalize_domain_name_lowercase():
    assert _normalize_domain_name("customer") == "Customer"


def test_normalize_domain_name_underscores():
    assert _normalize_domain_name("customer_ops") == "Customer Ops"


def test_normalize_domain_name_hyphens():
    assert _normalize_domain_name("supply-chain") == "Supply Chain"


def test_normalize_domain_name_mixed_case():
    assert _normalize_domain_name("REVENUE") == "Revenue"


def test_normalize_domain_name_extra_spaces():
    assert _normalize_domain_name("  human  resources  ") == "Human Resources"


# ---------------------------------------------------------------------------
# TableEnrichment model validation
# ---------------------------------------------------------------------------


def test_table_enrichment_tier_default():
    e = TableEnrichment(
        table_description="x",
        columns={},
    )
    assert e.tier == 3


def test_table_enrichment_tier_clamped():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TableEnrichment(table_description="x", columns={}, tier=6)
    with pytest.raises(ValidationError):
        TableEnrichment(table_description="x", columns={}, tier=0)
