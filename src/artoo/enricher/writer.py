from __future__ import annotations

import logging
import re

from ..catalog.openmetadata import OpenMetadataClient
from ..models import TableEnrichment

logger = logging.getLogger(__name__)


class CatalogWriter:
    def __init__(self, om_client: OpenMetadataClient) -> None:
        self.om = om_client
        # Tracks glossary terms created across all tables in this run to avoid redundant PUTs
        self._seen_glossary_terms: set[str] = set()

    async def write(self, table_fqn: str, enrichment: TableEnrichment) -> None:
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
            if col_indices.get(col_name) is None or not col_info.business_name:
                continue
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

        # Build column patch ops
        pii_count = 0
        sensitivity_count = 0
        for col_name, col_info in enrichment.columns.items():
            idx = col_indices.get(col_name)
            if idx is None:
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
