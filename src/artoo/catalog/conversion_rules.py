"""
Generate SQL conversion rules from UnidadesMedida glossary term tags.
"""

from artoo.catalog.units import UNIT_CONVERSION_MAP, get_conversion_factor
from artoo.models import TableDetail


def extract_unit_term(tag_fqn: str) -> str | None:
    """
    Extract unit term name from a glossary tag FQN.
    Example: "UnidadesMedida.Millones_EUR" → "Millones_EUR"
    """
    if not tag_fqn.startswith("UnidadesMedida."):
        return None
    return tag_fqn.split(".", 1)[1]


def generate_conversion_rules(tables: list[TableDetail]) -> str:
    """
    Generate a human-readable conversion rules section for the SQL prompt.
    
    Scans all columns for UnidadesMedida glossary term tags and builds:
    1. A list of columns with their unit tags
    2. Conversion factors between units (when applicable)
    3. Example conversions for common operations
    
    Returns empty string if no unit tags found.
    """
    # Collect (table.column, unit_term) pairs
    column_units: list[tuple[str, str, str]] = []  # (table_fqn, col_name, unit_term)
    
    for table in tables:
        for col in table.columns:
            for tag in col.tags:
                unit_term = extract_unit_term(tag)
                if unit_term and unit_term in UNIT_CONVERSION_MAP:
                    column_units.append((table.name, col.name, unit_term))
    
    if not column_units:
        return ""
    
    # Build the rules section
    lines = [
        "",
        "=== UNIT CONVERSION RULES (auto-generated from UnidadesMedida glossary) ===",
        "",
        "IMPORTANT: Apply these conversions when comparing or aggregating values with different units.",
        "",
    ]
    
    # Group by unit for clarity
    by_unit: dict[str, list[tuple[str, str]]] = {}
    for table_fqn, col_name, unit_term in column_units:
        by_unit.setdefault(unit_term, []).append((table_fqn, col_name))
    
    # List all columns with their units
    lines.append("Column Units:")
    for unit_term in sorted(by_unit.keys()):
        unit_info = UNIT_CONVERSION_MAP[unit_term]
        lines.append(f"  • {unit_info.display_name} (scale: {unit_info.scale_factor:,.0f})")
        for table_fqn, col_name in by_unit[unit_term]:
            # Extract short table name from FQN (e.g., "public.turismo" from "artoo-postgres.artoo_demo.public.turismo")
            short_table = ".".join(table_fqn.split(".")[-2:])
            lines.append(f"    - {short_table}.{col_name}")
    
    lines.append("")
    
    # Generate conversion examples for monetary units (most common case)
    monetary_units = {
        term: cols
        for term, cols in by_unit.items()
        if UNIT_CONVERSION_MAP[term].base_unit == "euros"
    }
    
    if len(monetary_units) > 1:
        lines.append("Conversion Examples (Monetary Units):")
        lines.append("")
        
        # Find pairs that need conversion
        for term1 in sorted(monetary_units.keys()):
            for term2 in sorted(monetary_units.keys()):
                if term1 == term2:
                    continue
                
                factor = get_conversion_factor(term1, term2)
                if factor is None:
                    continue
                
                # Get representative columns
                col1 = monetary_units[term1][0]  # (table_fqn, col_name)
                col2 = monetary_units[term2][0]
                
                short_table1 = ".".join(col1[0].split(".")[-2:])
                short_table2 = ".".join(col2[0].split(".")[-2:])
                
                unit1_info = UNIT_CONVERSION_MAP[term1]
                unit2_info = UNIT_CONVERSION_MAP[term2]
                
                lines.append(f"  Comparing {unit1_info.display_name} with {unit2_info.display_name}:")
                
                if factor > 1:
                    # term1 is larger unit (e.g., Millones → Euros)
                    lines.append(f"    ✓ CORRECT:   {short_table1}.{col1[1]} * {factor:,.0f} / {short_table2}.{col2[1]}")
                    lines.append(f"    ✗ WRONG:     {short_table1}.{col1[1]} / {short_table2}.{col2[1]}  -- units mismatch!")
                else:
                    # term1 is smaller unit (e.g., Euros → Millones)
                    lines.append(f"    ✓ CORRECT:   {short_table1}.{col1[1]} / {factor:,.0f} / {short_table2}.{col2[1]}")
                    lines.append(f"    ✗ WRONG:     {short_table1}.{col1[1]} / {short_table2}.{col2[1]}  -- units mismatch!")
                
                lines.append("")
    
    lines.append("=" * 70)
    lines.append("")
    
    return "\n".join(lines)


__all__ = ["generate_conversion_rules"]
