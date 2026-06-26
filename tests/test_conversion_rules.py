"""
Tests for unit conversion rules generation from glossary terms.
"""

from artoo.catalog.conversion_rules import extract_unit_term, generate_conversion_rules
from artoo.catalog.units import get_conversion_factor
from artoo.models import ColumnMeta, TableDetail


def test_extract_unit_term():
    """Test extraction of unit term from glossary tag FQN."""
    assert extract_unit_term("UnidadesMedida.Millones_EUR") == "Millones_EUR"
    assert extract_unit_term("UnidadesMedida.Euros") == "Euros"
    assert extract_unit_term("BusinessTerms.Revenue") is None
    assert extract_unit_term("PII.Sensitive") is None


def test_get_conversion_factor():
    """Test conversion factor calculation between unit terms."""
    # Millones → Euros = 1,000,000
    assert get_conversion_factor("Millones_EUR", "Euros") == 1_000_000.0
    
    # Miles → Euros = 1,000
    assert get_conversion_factor("Miles_EUR", "Euros") == 1_000.0
    
    # Euros → Millones = 0.000001
    assert get_conversion_factor("Euros", "Millones_EUR") == 1e-6
    
    # Miles → Millones = 0.001
    assert get_conversion_factor("Miles_EUR", "Millones_EUR") == 0.001
    
    # Incompatible units → None
    assert get_conversion_factor("Millones_EUR", "Porcentaje_0_100") is None
    assert get_conversion_factor("Euros", "Dias") is None
    
    # Unknown terms → None
    assert get_conversion_factor("UnknownUnit", "Euros") is None


def test_generate_conversion_rules_empty():
    """Test with tables that have no unit tags."""
    tables = [
        TableDetail(
            name="artoo-postgres.demo.public.users",
            description="User table",
            display_name="Users",
            business_domain=None,
            columns=[
                ColumnMeta(
                    name="id",
                    data_type="INT",
                    tags=["PII.Sensitive"],  # Non-unit tag
                ),
                ColumnMeta(
                    name="name",
                    data_type="VARCHAR",
                    tags=[],
                ),
            ],
            foreign_keys=[],
        )
    ]
    
    result = generate_conversion_rules(tables)
    assert result == ""


def test_generate_conversion_rules_single_unit():
    """Test with columns using the same unit (no conversion needed)."""
    tables = [
        TableDetail(
            name="artoo-postgres.demo.public.transactions",
            description="Transactions",
            display_name="Transactions",
            business_domain=None,
            columns=[
                ColumnMeta(
                    name="amount_eur",
                    data_type="NUMERIC",
                    tags=["UnidadesMedida.Euros"],
                ),
                ColumnMeta(
                    name="fee_eur",
                    data_type="NUMERIC",
                    tags=["UnidadesMedida.Euros"],
                ),
            ],
            foreign_keys=[],
        )
    ]
    
    result = generate_conversion_rules(tables)
    
    # Should include column listing but no conversion examples (same unit)
    assert "UNIT CONVERSION RULES" in result
    assert "Column Units:" in result
    assert "Euros" in result
    assert "public.transactions.amount_eur" in result
    assert "public.transactions.fee_eur" in result


def test_generate_conversion_rules_multi_unit():
    """Test with columns using different monetary units (conversion needed)."""
    tables = [
        TableDetail(
            name="artoo-postgres.demo.public.turismo",
            description="Tourism data",
            display_name="Tourism",
            business_domain=None,
            columns=[
                ColumnMeta(
                    name="gasto_medio_eur",
                    data_type="NUMERIC",
                    description="Average spend in euros",
                    tags=["UnidadesMedida.Euros"],
                ),
            ],
            foreign_keys=[],
        ),
        TableDetail(
            name="artoo-postgres.demo.public.indicadores_economicos",
            description="Economic indicators",
            display_name="Economic Indicators",
            business_domain=None,
            columns=[
                ColumnMeta(
                    name="pib_millones_eur",
                    data_type="NUMERIC",
                    description="GDP in millions of euros",
                    tags=["UnidadesMedida.Millones_EUR"],
                ),
            ],
            foreign_keys=[],
        ),
    ]
    
    result = generate_conversion_rules(tables)
    
    # Should include everything
    assert "UNIT CONVERSION RULES" in result
    assert "Column Units:" in result
    assert "Euros" in result
    assert "Millones de Euros" in result
    assert "public.turismo.gasto_medio_eur" in result
    assert "public.indicadores_economicos.pib_millones_eur" in result
    
    # Should include conversion examples
    assert "Conversion Examples (Monetary Units):" in result
    assert "CORRECT" in result
    assert "WRONG" in result
    assert "1,000,000" in result  # Conversion factor
    assert "units mismatch" in result


def test_generate_conversion_rules_three_units():
    """Test with Euros, Miles_EUR, and Millones_EUR."""
    tables = [
        TableDetail(
            name="artoo-postgres.demo.public.transactions",
            description="Transactions",
            display_name="Transactions",
            business_domain=None,
            columns=[
                ColumnMeta(name="amount_eur", data_type="NUMERIC", tags=["UnidadesMedida.Euros"]),
                ColumnMeta(
                    name="budget_k_eur", data_type="NUMERIC", tags=["UnidadesMedida.Miles_EUR"]
                ),
            ],
            foreign_keys=[],
        ),
        TableDetail(
            name="artoo-postgres.demo.public.economy",
            description="Economy",
            display_name="Economy",
            business_domain=None,
            columns=[
                ColumnMeta(
                    name="gdp_m_eur", data_type="NUMERIC", tags=["UnidadesMedida.Millones_EUR"]
                ),
            ],
            foreign_keys=[],
        ),
    ]
    
    result = generate_conversion_rules(tables)
    
    # All three units should be listed
    assert "Euros" in result
    assert "Miles de Euros" in result
    assert "Millones de Euros" in result
    
    # Multiple conversion pairs should exist
    assert result.count("CORRECT") >= 4  # At least 4 conversion examples (bidirectional)
    assert "1,000" in result or "1000" in result  # Miles conversion factor


def test_generate_conversion_rules_mixed_units():
    """Test with monetary + non-monetary units (should only show monetary conversions)."""
    tables = [
        TableDetail(
            name="artoo-postgres.demo.public.data",
            description="Mixed data",
            display_name="Data",
            business_domain=None,
            columns=[
                ColumnMeta(name="amount_eur", data_type="NUMERIC", tags=["UnidadesMedida.Euros"]),
                ColumnMeta(
                    name="gdp_m_eur", data_type="NUMERIC", tags=["UnidadesMedida.Millones_EUR"]
                ),
                ColumnMeta(
                    name="duration_days", data_type="INT", tags=["UnidadesMedida.Dias"]
                ),
                ColumnMeta(
                    name="rate_pct", data_type="NUMERIC", tags=["UnidadesMedida.Porcentaje_0_100"]
                ),
            ],
            foreign_keys=[],
        ),
    ]
    
    result = generate_conversion_rules(tables)
    
    # All units should be listed
    assert "Euros" in result
    assert "Millones de Euros" in result
    assert "Días" in result
    assert "Porcentaje" in result
    
    # But conversion examples should only exist for monetary units
    assert "Conversion Examples (Monetary Units):" in result
    assert "amount_eur" in result
    assert "gdp_m_eur" in result
    
    # Non-monetary columns should not appear in conversion examples section
    lines = result.split("Conversion Examples (Monetary Units):")[1]
    assert "duration_days" not in lines
    assert "rate_pct" not in lines
