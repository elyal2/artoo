from __future__ import annotations

import logging
import re

from ..catalog.openmetadata import OpenMetadataClient
from ..models import TableEnrichment

logger = logging.getLogger(__name__)


# Unit suffix patterns and their conversion factors
# Ordered by specificity (most specific first)
# Pattern strategy: require explicit underscore + unit suffix to avoid false positives
_UNIT_PATTERNS = [
    # ── MONETARY UNITS ──────────────────────────────────────────────────────
    # Millions
    (r"_millones?(_eur|_usd|_gbp|_chf)?$", "millions", "1 unit = 1,000,000"),
    (r"_mill(_eur|_usd|_gbp|_chf)?$", "millions", "1 unit = 1,000,000"),
    (r"_meur$", "millions of euros", "1 unit = 1,000,000€"),
    (r"_musd$", "millions of dollars", "1 unit = 1,000,000$"),
    (r"_mgbp$", "millions of pounds", "1 unit = 1,000,000£"),
    # Thousands
    (r"_miles?(_eur|_usd|_gbp|_chf)?$", "thousands", "1 unit = 1,000"),
    (r"_k(_eur|_usd|_gbp|_chf)?$", "thousands", "1 unit = 1,000"),  # common shorthand: revenue_k
    (r"_keur$", "thousands of euros", "1 unit = 1,000€"),
    (r"_kusd$", "thousands of dollars", "1 unit = 1,000$"),
    # Basis points (finance)
    (r"_bps$", "basis points", "1 unit = 0.01%, 100 bps = 1%"),
    # Generic monetary (only if explicitly named) - ORDERED BY LENGTH (longest first)
    (r"^(gross_|total_|unit_|net_)?(importe|amount|price|monto|cost)$", "monetary value", "Check schema for currency unit"),
    (r"^(facturacion|ingresos|revenue)$", "monetary value", "Check schema for currency unit"),
    (r"^(nightly_rate|daily_rate|revpar|adr)$", "rate per unit", "Check schema for currency unit"),
    (r"_importe_eur$", "euros", "1 unit = 1€"),
    (r"_monto_eur$", "euros", "1 unit = 1€"),
    (r"_valor_eur$", "euros", "1 unit = 1€"),
    (r"_precio_eur$", "euros", "1 unit = 1€"),
    (r"_coste_eur$", "euros", "1 unit = 1€"),
    (r"_gasto.*_eur$", "euros", "1 unit = 1€"),
    # Currency suffixes with plural support (ORDERED: longest first)
    (r"_euros?$", "euros", "1 unit = 1€"),
    (r"_(dollars?|usd)$", "US dollars", "1 unit = 1$"),  # dollars (7) > dollar (6) > usd (3)
    (r"_(pounds?|gbp)$", "British pounds", "1 unit = 1£"),  # pounds (6) > pound (5) > gbp (3)
    
    # ── PERCENTAGES & RATIOS ────────────────────────────────────────────────
    (r"_pct$", "percentage", "1 unit = 1%, range 0-100, divide by 100 for decimal"),
    (r"_percent(age)?$", "percentage", "1 unit = 1%, range 0-100, divide by 100 for decimal"),
    (r"_tasa_pct$", "percentage rate", "1 unit = 1%, range 0-100, divide by 100 for decimal"),
    (r"_ratio$", "ratio", "Decimal ratio (0.0-1.0), not percentage. Multiply by 100 for percentage."),
    (r"_index$", "index value", "Decimal or normalized index. Check schema for scale."),
    
    # ── TIME & DATES ────────────────────────────────────────────────────────
    (r"_days?$", "days", "1 unit = 1 day = 24 hours"),
    (r"_d\b$", "days", "1 unit = 1 day"),  # word boundary to avoid 'id', 'pid'
    (r"_months?$", "months", "1 unit = 1 month"),
    (r"_mo$", "months", "1 unit = 1 month"),  # safer than _m alone
    (r"_years?$", "years", "1 unit = 1 year"),
    (r"_yr$", "years", "1 unit = 1 year"),
    (r"_y\b$", "years", "1 unit = 1 year"),  # word boundary
    (r"_hours?$", "hours", "1 unit = 1 hour = 60 minutes"),
    (r"_h\b$", "hours", "1 unit = 1 hour"),  # word boundary
    (r"_minutes?$", "minutes", "1 unit = 1 minute = 60 seconds"),
    (r"_min$", "minutes", "1 unit = 1 minute"),
    (r"_seconds?$", "seconds", "1 unit = 1 second"),
    (r"_sec$", "seconds", "1 unit = 1 second"),
    (r"_s\b$", "seconds", "1 unit = 1 second"),  # word boundary to avoid 'status'
    
    # ── COUNTS & QUANTITIES ─────────────────────────────────────────────────
    (r"_qty$", "quantity", "Count of physical items or units (not monetary)"),
    (r"_quantity$", "quantity", "Count of physical items or units (not monetary)"),
    (r"_units?$", "units", "Count of discrete items (not monetary)"),
    (r"_count$", "count", "Integer count"),
    (r"_freq(uency)?$", "frequency", "Occurrence frequency. Check schema for time period."),
    
    # ── HOSPITALITY METRICS ─────────────────────────────────────────────────
    (r"_rooms?$", "rooms", "Count of hotel rooms (inventory or occupied)"),
    (r"_keys?$", "rooms", "Count of hotel rooms (inventory)"),
    (r"_noches?$", "nights", "Count of nights stayed (room-nights)"),
    (r"_nights?$", "nights", "Count of nights stayed"),
    (r"_pax$", "passengers/guests", "Count of people (from Latin 'pax')"),
    (r"_guests?$", "guests", "Count of guests/visitors"),
    (r"_huespedes?$", "guests", "Count of guests (Spanish)"),
    
    # ── WEIGHTS & VOLUMES ───────────────────────────────────────────────────
    (r"_kilograms?$", "kilograms", "1 unit = 1 kg = 1,000 grams"),
    (r"_kg$", "kilograms", "1 unit = 1 kg = 1,000 grams"),
    (r"_grams?$", "grams", "1 unit = 1 gram"),
    (r"_gr$", "grams", "1 unit = 1 gram"),
    (r"_g\b$", "grams", "1 unit = 1 gram"),  # word boundary to avoid 'rating', 'marketing'
    (r"_tons?$", "tons", "1 unit = 1 metric ton = 1,000 kg"),
    (r"_toneladas?$", "tons", "1 unit = 1,000 kg"),
    (r"_mt$", "metric tons", "1 unit = 1,000 kg"),
    (r"_lb$", "pounds", "1 unit = 1 lb ≈ 0.453592 kg"),
    (r"_lbs$", "pounds", "1 unit = 1 lb"),
    (r"_oz$", "ounces", "1 unit = 1 oz ≈ 28.3495 grams"),
    (r"_liters?$", "liters", "1 unit = 1 liter"),
    (r"_l\b$", "liters", "1 unit = 1 liter"),  # word boundary to avoid 'email', 'total'
    (r"_ml$", "milliliters", "1 unit = 1 ml = 0.001 liters"),
    (r"_gallons?$", "gallons", "1 unit = 1 gallon ≈ 3.78541 liters"),
    (r"_gal$", "gallons", "1 unit = 1 gallon"),
]


def _add_unit_documentation(col_name: str, description: str) -> str:
    """
    Detect unit suffix in column name and append conversion factor to description
    if not already present.
    """
    if not description:
        return description
    
    # Check if description already contains conversion factor pattern
    if re.search(r"\(1 unit =", description, re.IGNORECASE):
        return description
    
    # Try each pattern (in order of specificity)
    for pattern, unit_name, conversion in _UNIT_PATTERNS:
        if re.search(pattern, col_name, re.IGNORECASE):
            # Append conversion factor to description
            return f"{description.rstrip('.')}. Unit: {unit_name} ({conversion})."
    
    return description


def _infer_unit_glossary_term(col_name: str) -> str | None:
    """
    Map column name to standardized UnidadesMedida glossary term.
    Returns the term name (e.g., "Millones_EUR") or None if no match.
    """
    col_lower = col_name.lower()
    
    # Ordered by specificity (most specific first)
    # Match patterns: pib_millones_eur, revenue_millones, gdp_mill_eur, etc.
    if re.search(r"_(millones?|mill)(_eur|_usd)?$", col_lower):
        return "Millones_EUR"
    if re.search(r"_meur$", col_lower):
        return "Millones_EUR"
    
    # Match patterns: budget_miles_eur, amount_k_eur, cost_keur
    if re.search(r"_(miles?|k)(_eur|_usd)?$", col_lower):
        return "Miles_EUR"
    if re.search(r"_keur$", col_lower):
        return "Miles_EUR"
    
    # Match patterns: rate_pct, tasa_pct, percentage, percent
    if re.search(r"_(pct|percent(age)?|tasa_pct)$", col_lower):
        return "Porcentaje_0_100"
    
    if re.search(r"_ratio$", col_lower):
        return "Ratio_Decimal"
    
    # Match patterns: duration_days, stay_d
    if re.search(r"_days?$", col_lower):
        return "Dias"
    if re.search(r"_d$", col_lower):
        return "Dias"
    
    # Match patterns: quantity, count, units, numero_*
    if re.search(r"_(qty|count|units?)$", col_lower):
        return "Unidades_Fisicas"
    if re.search(r"^numero_", col_lower):
        return "Unidades_Fisicas"
    
    # Default: no unit term
    return None


class CatalogWriter:
    def __init__(self, om_client: OpenMetadataClient) -> None:
        self.om = om_client
        # Tracks glossary terms created across all tables in this run to avoid redundant PUTs
        self._seen_glossary_terms: set[str] = set()

    async def write(self, table_fqn: str, enrichment: TableEnrichment) -> None:
        # Post-process: add unit documentation to column descriptions
        for col_name, col_info in enrichment.columns.items():
            if col_info.description:
                col_info.description = _add_unit_documentation(col_name, col_info.description)
        
        # Build a single patch with table description + displayName + all column patches
        ops: list[dict[str, object]] = [
            {"op": "add", "path": "/description", "value": enrichment.table_description},
        ]

        # Set table displayName from business domain if available
        if enrichment.business_domain:
            display_name = _normalize_domain_name(enrichment.business_domain)
            ops.append({"op": "add", "path": "/displayName", "value": display_name})

        # Get column indices once if we have column enrichments
        col_indices: dict[str, int] = {}
        if enrichment.columns:
            try:
                col_indices = await self.om.get_column_indices(table_fqn)
            except Exception as exc:
                logger.warning("Could not get column indices for %s: %s", table_fqn, exc)

        # Pre-resolve glossary terms for all columns before building the patch so
        # each column's tag list is complete when we do the single replace per column.
        glossary_terms: dict[str, str] = {}  # col_name -> term FQN
        for col_name, col_info in enrichment.columns.items():
            if col_indices.get(col_name) is None:
                continue
            
            # Business term from LLM enrichment
            if col_info.business_name:
                try:
                    term_name = _slug_to_pascal(col_info.business_name)
                    if term_name not in self._seen_glossary_terms:
                        await self.om.ensure_glossary_term(
                            "BusinessTerms", term_name, col_info.business_name, col_info.description
                        )
                        self._seen_glossary_terms.add(term_name)
                    glossary_terms[col_name] = f"BusinessTerms.{term_name}"
                except Exception as exc:
                    logger.warning(
                        "Could not create glossary term for %s.%s: %s", table_fqn, col_name, exc
                    )
            
            # Unit of measure term (auto-inferred from column name)
            unit_term = _infer_unit_glossary_term(col_name)
            if unit_term:
                logger.info("Inferred unit term '%s' for column %s.%s", unit_term, table_fqn, col_name)
                glossary_terms[f"{col_name}__unit"] = f"UnidadesMedida.{unit_term}"
            else:
                logger.debug("No unit term inferred for column %s.%s", table_fqn, col_name)

        # Build column patch ops
        pii_count = 0
        sensitivity_count = 0
        for col_name, col_info in enrichment.columns.items():
            idx = col_indices.get(col_name)
            if idx is None:
                logger.warning("Skipping column %s.%s (not found in indices)", table_fqn, col_name)
                continue
            if col_info.description:
                ops.append(
                    {
                        "op": "add",
                        "path": f"/columns/{idx}/description",
                        "value": col_info.description,
                    }
                )
            if col_info.business_name:
                ops.append(
                    {
                        "op": "add",
                        "path": f"/columns/{idx}/displayName",
                        "value": col_info.business_name,
                    }
                )

            # Build the complete desired tag list and replace atomically.
            # Using "replace" instead of "add" ensures re-runs clean up stale tags
            # from previous enrichment passes rather than accumulating duplicates.
            col_tags: list[dict[str, object]] = []
            if col_info.pii:
                col_tags.append(
                    {"tagFQN": "PII.Sensitive", "labelType": "Automated", "state": "Confirmed"}
                )
                if col_info.pii_type:
                    pii_tag = _pii_type_tag(col_info.pii_type)
                    if pii_tag:
                        col_tags.append(
                            {"tagFQN": pii_tag, "labelType": "Automated", "state": "Confirmed"}
                        )
                pii_count += 1

            # Coerce: a PII column must never be tagged Public regardless of LLM output
            sensitivity_value = col_info.sensitivity
            if col_info.pii and sensitivity_value == "public":
                sensitivity_value = "confidential"
            sensitivity_tag = _sensitivity_tag(sensitivity_value)
            if sensitivity_tag:
                col_tags.append(
                    {
                        "tagFQN": sensitivity_tag,
                        "labelType": "Automated",
                        "state": "Confirmed",
                    }
                )
                sensitivity_count += 1

            if col_name in glossary_terms:
                col_tags.append(
                    {
                        "tagFQN": glossary_terms[col_name],
                        "labelType": "Automated",
                        "state": "Confirmed",
                        "source": "Glossary",
                    }
                )
            
            # Add unit glossary term if present
            unit_key = f"{col_name}__unit"
            if unit_key in glossary_terms:
                unit_tag_fqn = glossary_terms[unit_key]
                logger.info("Adding unit tag '%s' to column %s.%s", unit_tag_fqn, table_fqn, col_name)
                col_tags.append(
                    {
                        "tagFQN": unit_tag_fqn,
                        "labelType": "Automated",
                        "state": "Confirmed",
                        "source": "Glossary",
                    }
                )

            ops.append({"op": "replace", "path": f"/columns/{idx}/tags", "value": col_tags})

        # Send single PATCH for table + columns — try FQN first, fallback to ID
        try:
            await self.om.patch_table(table_fqn, ops)
            logger.info("Updated table description for %s", table_fqn)
        except Exception:
            # Fallback: patch by ID (handles corrupted FQN index)
            try:
                table_id = await self.om.get_table_id(table_fqn)
                await self.om.patch_table_by_id(table_id, ops)
                logger.info("Updated table description for %s (via ID fallback)", table_fqn)
            except Exception as exc2:
                logger.warning("Could not patch %s: %s", table_fqn, exc2)
                return

        # Apply table-level tags separately (best-effort)
        table_tags: list[str] = [f"Business.{t}" for t in enrichment.suggested_tags]
        tier_tag = f"Tier.Tier{enrichment.tier}"
        if tier_tag not in table_tags:
            table_tags.append(tier_tag)
        if table_tags:
            try:
                await self.om.put_table_tags(table_fqn, table_tags)
                logger.info("Applied %d table tags to %s", len(table_tags), table_fqn)
            except Exception as exc:
                logger.warning("Could not apply tags to %s: %s", table_fqn, exc)

        # Domain assignment (best-effort)
        if enrichment.business_domain:
            try:
                domain_name = _normalize_domain_name(enrichment.business_domain)
                domain_id = await self.om.get_domain_id(domain_name)
                if domain_id is None:
                    domain_id = await self.om.ensure_domain(
                        domain_name, enrichment.table_description
                    )
                await self.om.patch_table(
                    table_fqn,
                    [
                        {
                            "op": "add",
                            "path": "/domain",
                            "value": {
                                "id": domain_id,
                                "type": "domain",
                                "name": domain_name,
                                "fullyQualifiedName": domain_name,
                            },
                        }
                    ],
                )
            except Exception as exc:
                logger.warning("Could not assign domain to %s: %s", table_fqn, exc)

        # Common queries custom property (best-effort)
        if enrichment.common_queries:
            try:
                common_queries = "\n".join(f"- {q}" for q in enrichment.common_queries)
                await self.om.patch_table(
                    table_fqn,
                    [
                        {
                            "op": "add",
                            "path": "/extension",
                            "value": {"commonQueries": common_queries},
                        }
                    ],
                )
            except Exception as exc:
                logger.warning("Could not set custom properties for %s: %s", table_fqn, exc)

        logger.info(
            "Enriched %s — %d columns, %d PII, %d sensitivity, tier=%d, domain=%s, %d glossary terms",
            table_fqn,
            len(enrichment.columns),
            pii_count,
            sensitivity_count,
            enrichment.tier,
            enrichment.business_domain,
            len(glossary_terms),
        )


__all__ = ["CatalogWriter"]


def _pii_type_tag(pii_type: str) -> str | None:
    mapping = {
        "name": "PIIType.Name",
        "email": "PIIType.Email",
        "phone": "PIIType.Phone",
        "dob": "PIIType.DateOfBirth",
        "national_id": "PIIType.NationalID",
    }
    return mapping.get(pii_type)


def _sensitivity_tag(sensitivity: str) -> str | None:
    mapping = {
        "public": "DataSensitivity.Public",
        "internal": "DataSensitivity.Internal",
        "confidential": "DataSensitivity.Confidential",
        "restricted": "DataSensitivity.Restricted",
    }
    return mapping.get(sensitivity)


def _slug_to_pascal(text: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _normalize_domain_name(text: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.title()
