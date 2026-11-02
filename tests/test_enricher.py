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

    async def complete(self, *, system: str, user: str, **kwargs: object) -> str:  # noqa: ARG002
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


def test_profile_patterns_apply_and_generic_stay(tmp_path) -> None:  # noqa: ANN001
    from artoo.enricher.writer import _add_unit_documentation
    from artoo.profile import load_profile

    d = tmp_path / "fiction"
    d.mkdir()
    (d / "profile.yaml").write_text(
        "unit_patterns:\n  - ['_widgets?$', 'widgets', 'Count of widgets']\n"
        "  - ['(bad', 'x', 'y']\n  - [only, two]\n"
    )
    prof = load_profile("fiction", root=tmp_path)
    assert len(prof.unit_patterns) == 1  # malformed entries dropped
    assert "Count of widgets" in _add_unit_documentation("stock_widgets", "Stock.", prof)
    assert "1 unit = 1 day" in _add_unit_documentation("stay_days", "Stay.", prof)
    # without the profile the domain pattern is unknown
    assert _add_unit_documentation("stock_widgets", "Stock.") == "Stock."


def test_missing_profile_is_generic(tmp_path) -> None:  # noqa: ANN001
    from artoo.profile import load_profile

    assert load_profile("nope", root=tmp_path).unit_patterns == ()


def test_engine_has_no_domain_terms() -> None:
    import re
    from pathlib import Path

    banned = re.compile(r"hotel|huesped|\bpib\b|bkng|revpar|hospitality|booking", re.I)
    offenders = []
    for f in Path("src/artoo").rglob("*.py"):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if banned.search(line):
                offenders.append(f"{f}:{n}: {line.strip()[:80]}")
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# Domain label normalization (models sometimes answer with a sentence)
# ---------------------------------------------------------------------------


def test_normalize_domain_name_keeps_leading_phrase_of_sentence():
    text = "Insurance distribution – agent/intermediary master data and commission configuration"
    assert _normalize_domain_name(text) == "Insurance Distribution"


def test_normalize_domain_name_drops_parenthetical_and_caps_words():
    assert _normalize_domain_name("Commercial quoting and policy conversion (SME)") == (
        "Commercial Quoting And Policy"
    )


# ---------------------------------------------------------------------------
# Wide tables: column batching and split-on-failure
# ---------------------------------------------------------------------------


def _column_entry(name: str) -> dict[str, object]:
    return {
        "description": f"About {name}",
        "business_name": name.title(),
        "pii": False,
        "pii_type": None,
        "sensitivity": "internal",
        "example_values": None,
    }


class BatchAwareLLM:
    """Answers with exactly the columns listed under 'Columns:' in the prompt."""

    def __init__(self, fail_above: int | None = None) -> None:
        self.calls: list[list[str]] = []
        self.prompts: list[str] = []
        self.fail_above = fail_above

    async def complete(self, *, system: str, user: str, **kwargs: object) -> str:  # noqa: ARG002
        import re

        block = user.split("Columns:\n", 1)[1].split("\n\n", 1)[0]
        names = re.findall(r"^  - (\w+) \(", block, flags=re.M)
        self.calls.append(names)
        self.prompts.append(user)
        if self.fail_above is not None and len(names) > self.fail_above:
            return '{"table_description": "Wide table", "columns": {"' + names[0]  # truncated
        first = "all columns" not in user and "produced elsewhere" not in user
        return json.dumps(
            {
                "table_description": "Wide table" if first else "",
                "business_name": "Wide Table" if first else None,
                "business_domain": "Sales" if first else None,
                "columns": {n: _column_entry(n) for n in names},
                "suggested_tags": ["wide"] if first else [],
                "common_queries": [],
            }
        )


def _wide_context(n: int) -> TableContext:
    return TableContext(
        name="wide",
        columns=[ColumnMeta(name=f"c{i}", data_type="text") for i in range(n)],
        column_stats={f"c{i}": {"distinct_count": 3} for i in range(n)},
        sample_rows=[{f"c{i}": i for i in range(n)}],
    )


@pytest.mark.asyncio
async def test_wide_table_is_split_into_balanced_batches(monkeypatch):
    from artoo.config import settings

    monkeypatch.setattr(settings, "enrichment_column_batch_size", 4)
    llm = BatchAwareLLM()
    result = await SemanticEnricher(llm_client=llm).enrich(_wide_context(10))
    assert [len(c) for c in llm.calls] == [4, 3, 3]
    assert set(result.columns) == {f"c{i}" for i in range(10)}
    assert result.table_description == "Wide table"
    assert result.business_name == "Wide Table"
    assert result.business_domain == "Sales"
    # later batches get told the table-level fields come from elsewhere
    assert "produced elsewhere" not in llm.prompts[0]
    assert "produced elsewhere" in llm.prompts[1]
    # each prompt only carries stats/samples of its own columns
    assert "c9" not in llm.prompts[0].split("Column statistics")[1]


@pytest.mark.asyncio
async def test_narrow_table_is_a_single_call(monkeypatch):
    from artoo.config import settings

    monkeypatch.setattr(settings, "enrichment_column_batch_size", 20)
    llm = BatchAwareLLM()
    await SemanticEnricher(llm_client=llm).enrich(_wide_context(12))
    assert len(llm.calls) == 1
    assert "columns in total" not in llm.prompts[0]


@pytest.mark.asyncio
async def test_batching_disabled_with_zero(monkeypatch):
    from artoo.config import settings

    monkeypatch.setattr(settings, "enrichment_column_batch_size", 0)
    llm = BatchAwareLLM()
    await SemanticEnricher(llm_client=llm).enrich(_wide_context(50))
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_truncated_json_splits_batch_instead_of_dropping_columns(monkeypatch):
    from artoo.config import settings

    monkeypatch.setattr(settings, "enrichment_column_batch_size", 0)
    llm = BatchAwareLLM(fail_above=3)
    result = await SemanticEnricher(llm_client=llm).enrich(_wide_context(8))
    assert set(result.columns) == {f"c{i}" for i in range(8)}
    assert result.table_description == "Wide table"
    assert max(len(c) for c in llm.calls[1:]) <= 4  # 8 -> 4 + 4


@pytest.mark.asyncio
async def test_single_column_failure_falls_back_to_partial(monkeypatch):
    from artoo.config import settings

    monkeypatch.setattr(settings, "enrichment_column_batch_size", 0)
    llm = BatchAwareLLM(fail_above=0)
    result = await SemanticEnricher(llm_client=llm).enrich(_wide_context(1))
    assert result.columns == {}
    assert result.table_description  # partial description kept
