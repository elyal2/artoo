"""
Unit conversion metadata for UnidadesMedida glossary terms.
Maps glossary term names to their conversion factors and semantic info.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitInfo:
    """Metadata for a unit of measure glossary term."""
    
    term_name: str
    display_name: str
    base_unit: str
    scale_factor: float  # Multiply by this to convert TO base unit
    description: str


# Glossary term → conversion metadata
UNIT_CONVERSION_MAP: dict[str, UnitInfo] = {
    # Monetary units
    "Millones_EUR": UnitInfo(
        term_name="Millones_EUR",
        display_name="Millones de Euros",
        base_unit="euros",
        scale_factor=1_000_000.0,
        description="1 unit = 1,000,000€. Multiply by 1,000,000 to get euros.",
    ),
    "Miles_EUR": UnitInfo(
        term_name="Miles_EUR",
        display_name="Miles de Euros",
        base_unit="euros",
        scale_factor=1_000.0,
        description="1 unit = 1,000€. Multiply by 1,000 to get euros.",
    ),
    "Euros": UnitInfo(
        term_name="Euros",
        display_name="Euros",
        base_unit="euros",
        scale_factor=1.0,
        description="Base monetary unit. 1 unit = 1€.",
    ),
    
    # Percentages and ratios
    "Porcentaje_0_100": UnitInfo(
        term_name="Porcentaje_0_100",
        display_name="Porcentaje (0-100)",
        base_unit="percentage",
        scale_factor=1.0,
        description="Range 0-100. Divide by 100 to convert to decimal ratio.",
    ),
    "Ratio_Decimal": UnitInfo(
        term_name="Ratio_Decimal",
        display_name="Ratio (0.0-1.0)",
        base_unit="ratio",
        scale_factor=1.0,
        description="Decimal ratio 0.0-1.0. Multiply by 100 to convert to percentage.",
    ),
    
    # Time
    "Dias": UnitInfo(
        term_name="Dias",
        display_name="Días",
        base_unit="days",
        scale_factor=1.0,
        description="1 unit = 1 day = 24 hours.",
    ),
    
    # Counts
    "Unidades_Fisicas": UnitInfo(
        term_name="Unidades_Fisicas",
        display_name="Unidades Físicas",
        base_unit="count",
        scale_factor=1.0,
        description="Count of discrete items (non-monetary).",
    ),
}


def get_conversion_factor(from_term: str, to_term: str) -> float | None:
    """
    Calculate conversion factor from one unit term to another.
    Returns None if units are incompatible (different base_unit).
    
    Example:
        get_conversion_factor("Millones_EUR", "Euros") → 1_000_000.0
        get_conversion_factor("Miles_EUR", "Millones_EUR") → 0.001
    """
    from_info = UNIT_CONVERSION_MAP.get(from_term)
    to_info = UNIT_CONVERSION_MAP.get(to_term)
    
    if not from_info or not to_info:
        return None
    
    # Can only convert between same base unit
    if from_info.base_unit != to_info.base_unit:
        return None
    
    # Factor = (from_scale / to_scale)
    # Example: Millones → Euros = 1M / 1 = 1,000,000
    # Example: Miles → Millones = 1K / 1M = 0.001
    return from_info.scale_factor / to_info.scale_factor


__all__ = ["UnitInfo", "UNIT_CONVERSION_MAP", "get_conversion_factor"]
