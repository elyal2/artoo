from __future__ import annotations

import base64
import logging
from typing import Any, Iterable, List
from urllib.parse import quote

import httpx

from ..config import settings
from ..models import ColumnMeta, SchemaColumn, TableDetail, TableSummary

logger = logging.getLogger(__name__)


async def _login_token(base_url: str) -> str:
    """Obtain a JWT token via admin login (default OM credentials)."""
    password = base64.b64encode(b"admin").decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/api/v1/users/login",
            headers={"Content-Type": "application/json"},
            json={"email": "admin@open-metadata.org", "password": password},
        )
        resp.raise_for_status()
        token = resp.json().get("accessToken")
        if not token:
            raise RuntimeError("No accessToken in OpenMetadata login response")
        logger.info("Obtained JWT token from OpenMetadata login")
        return str(token)


class OpenMetadataClient:
    def __init__(self, base_url: str, api_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._client = httpx.AsyncClient(timeout=30)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _refresh_token(self) -> None:
        """Re-authenticate and update the stored token."""
        self.api_token = await _login_token(self.base_url)

    async def _get(self, url: str) -> httpx.Response:
        resp = await self._client.get(url, headers=self._headers())
        if resp.status_code == 401:
            await self._refresh_token()
            resp = await self._client.get(url, headers=self._headers())
        return resp

    async def _post(self, url: str, json: Any) -> httpx.Response:
        resp = await self._client.post(url, headers=self._headers(), json=json)
        if resp.status_code == 401:
            await self._refresh_token()
            resp = await self._client.post(url, headers=self._headers(), json=json)
        return resp

    async def _patch(self, url: str, json: Any) -> httpx.Response:
        patch_headers = {**self._headers(), "Content-Type": "application/json-patch+json"}
        resp = await self._client.patch(url, headers=patch_headers, json=json)
        if resp.status_code == 401:
            await self._refresh_token()
            patch_headers = {**self._headers(), "Content-Type": "application/json-patch+json"}
            resp = await self._client.patch(url, headers=patch_headers, json=json)
        return resp

    async def _put(self, url: str, json: Any) -> httpx.Response:
        resp = await self._client.put(url, headers=self._headers(), json=json)
        if resp.status_code == 401:
            await self._refresh_token()
            resp = await self._client.put(url, headers=self._headers(), json=json)
        return resp

    async def list_tables(self) -> List[TableSummary]:
        all_items: list[TableSummary] = []
        after: str | None = None
        db_filter = settings.openmetadata_db_filter
        while True:
            url = f"{self.base_url}/api/v1/tables?fields=description,tags,usageSummary&limit=100"
            if db_filter:
                url += f"&database={quote(db_filter, safe='')}"
            if after:
                url += f"&after={quote(after, safe='')}"
            resp = await self._get(url)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
            for item in data:
                fqn = item.get("fullyQualifiedName", item.get("name", ""))
                if any(s in fqn for s in ("information_schema", "pg_catalog")):
                    continue
                # Domain is not available in list endpoint; fetch per-table if needed
                all_items.append(
                    TableSummary(
                        name=fqn,
                        description=item.get("description"),
                        business_domain=None,
                    )
                )
            paging = payload.get("paging", {})
            after = paging.get("after")
            if not after:
                break
        return all_items

    async def get_table(self, fqn: str) -> TableDetail:
        url = (
            f"{self.base_url}/api/v1/tables/name/{fqn}"
            "?fields=columns,tableConstraints,usageSummary,domains"
        )
        resp = await self._get(url)
        resp.raise_for_status()
        raw = resp.json()

        cols = [
            ColumnMeta(
                name=c["name"],
                data_type=c.get("dataType", ""),
                description=c.get("description"),
                business_name=c.get("displayName"),
                foreign_key=self._fk_name(c),
            )
            for c in raw.get("columns", [])
        ]
        # domains is a list in 1.12.x — take the first entry's name
        domains: list[Any] = raw.get("domains") or []
        business_domain = self._domain_name(domains[0]) if domains else None
        return TableDetail(
            name=raw.get("fullyQualifiedName", raw.get("name")),
            description=raw.get("description"),
            display_name=raw.get("displayName"),
            business_domain=business_domain,
            columns=cols,
            foreign_keys=[fk for fk in (self._fk_name(c) for c in raw.get("columns", [])) if fk],
        )
        resp = await self._get(url)
        resp.raise_for_status()
        raw = resp.json()

        # Build per-column example values from sampleData if available.
        # sampleData.columns is a list of column names; sampleData.rows is a list of value lists.
        sample_by_col: dict[str, list[str]] = {}
        sample_data = raw.get("sampleData") or {}
        sample_cols: list[str] = sample_data.get("columns") or []
        sample_rows: list[list[Any]] = sample_data.get("rows") or []
        if sample_cols and sample_rows:
            for idx, col_name in enumerate(sample_cols):
                seen: list[str] = []
                for row in sample_rows[:5]:
                    if idx < len(row) and row[idx] is not None:
                        val = str(row[idx])
                        if val not in seen:
                            seen.append(val)
                if seen:
                    sample_by_col[col_name] = seen

        cols = [
            ColumnMeta(
                name=c["name"],
                data_type=c.get("dataType", ""),
                description=c.get("description"),
                business_name=c.get("displayName"),
                foreign_key=self._fk_name(c),
                example_values=", ".join(sample_by_col[c["name"]])
                if c["name"] in sample_by_col
                else None,
            )
            for c in raw.get("columns", [])
        ]
        return TableDetail(
            name=raw.get("fullyQualifiedName", raw.get("name")),
            description=raw.get("description"),
            display_name=raw.get("displayName"),
            business_domain=self._domain_name(raw.get("domain")),
            columns=cols,
            foreign_keys=[fk for fk in (self._fk_name(c) for c in raw.get("columns", [])) if fk],
        )

    @staticmethod
    def schema_columns(table: TableDetail) -> list[SchemaColumn]:
        return [
            SchemaColumn(
                name=col.name,
                data_type=col.data_type,
                is_temporal=OpenMetadataClient._is_temporal_type(col.data_type, col.name),
                is_numeric=OpenMetadataClient._is_numeric_type(col.data_type),
            )
            for col in table.columns
        ]

    @staticmethod
    def _is_temporal_type(data_type: str, name: str) -> bool:
        dtype = data_type.lower()
        n = name.lower()
        return any(t in dtype for t in ("date", "time", "timestamp")) or any(
            hint in n for hint in ("date", "time", "month", "year", "day")
        )

    @staticmethod
    def _is_numeric_type(data_type: str) -> bool:
        dtype = data_type.lower()
        return any(t in dtype for t in ("int", "numeric", "decimal", "double", "real", "float"))

    @staticmethod
    def _fk_name(column: dict[str, Any]) -> str | None:
        constraints = column.get("constraint") or ""
        if constraints and isinstance(constraints, str) and constraints.lower() == "foreignkey":
            fk = column.get("foreignKeys") or column.get("foreignKeyData")
            if fk and isinstance(fk, Iterable):
                target = next(iter(fk), None)
                if target and isinstance(target, dict):
                    return f"{target.get('table')}.{target.get('column') or target.get('name')}"
        return None

    async def semantic_search(self, query: str, n_results: int = 5) -> list[TableDetail]:
        encoded_q = quote(query, safe="")
        url = f"{self.base_url}/api/v1/search/query?q={encoded_q}&index=table_search_index&from=0&size={n_results}"
        resp = await self._get(url)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        results: list[TableDetail] = []
        for hit in hits:
            source = hit.get("_source", {})
            fqn = source.get("fullyQualifiedName")
            if fqn:
                try:
                    results.append(await self.get_table(fqn))
                except httpx.HTTPStatusError as exc:
                    logger.warning("Failed to fetch table %s: %s", fqn, exc)
        return results

    async def patch_table(self, fqn: str, payload: list[dict[str, Any]]) -> None:
        url = f"{self.base_url}/api/v1/tables/name/{fqn}"
        resp = await self._patch(url, payload)
        resp.raise_for_status()

    async def get_table_id(self, fqn: str) -> str:
        """Get table UUID by FQN lookup, falling back to name search within the configured db filter."""
        short_name = fqn.split(".")[-1]
        db_filter = settings.openmetadata_db_filter
        url = f"{self.base_url}/api/v1/tables?fields=id,name&limit=100"
        if db_filter:
            url += f"&database={quote(db_filter, safe='')}"
        resp = await self._get(url)
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            if item.get("name") == short_name:
                return str(item["id"])
        raise ValueError(f"Table ID not found for {fqn}")

    async def patch_table_by_id(self, table_id: str, payload: list[dict[str, Any]]) -> None:
        url = f"{self.base_url}/api/v1/tables/{table_id}"
        resp = await self._patch(url, payload)
        resp.raise_for_status()

    async def get_column_indices(self, fqn: str) -> dict[str, int]:
        """Return a mapping of column_name -> index for a table."""
        url = f"{self.base_url}/api/v1/tables/name/{fqn}?fields=columns"
        resp = await self._get(url)
        resp.raise_for_status()
        cols = resp.json().get("columns", [])
        return {c["name"]: i for i, c in enumerate(cols)}

    async def put_table_tags(self, fqn: str, tags: list[str]) -> None:
        tag_payloads = [{"tagFQN": t} for t in tags]
        payload = [{"op": "replace", "path": "/tags", "value": tag_payloads}]
        await self.patch_table(fqn, payload)

    @staticmethod
    def _domain_name(domain: Any) -> str | None:
        if isinstance(domain, dict):
            name = domain.get("name") or domain.get("fullyQualifiedName")
            return str(name) if name else None
        if isinstance(domain, str):
            return domain
        return None

    async def ensure_classification(
        self, name: str, description: str, mutually_exclusive: bool = False
    ) -> None:
        payload = {
            "name": name,
            "description": description,
            "mutuallyExclusive": mutually_exclusive,
        }
        resp = await self._put(f"{self.base_url}/api/v1/classifications", payload)
        resp.raise_for_status()

    async def ensure_tag(self, classification: str, name: str, description: str) -> None:
        payload = {
            "name": name,
            "classification": classification,
            "description": description,
        }
        resp = await self._put(f"{self.base_url}/api/v1/tags", payload)
        resp.raise_for_status()

    async def ensure_glossary(self, name: str, display_name: str, description: str) -> None:
        payload = {"name": name, "displayName": display_name, "description": description}
        resp = await self._put(f"{self.base_url}/api/v1/glossaries", payload)
        resp.raise_for_status()

    async def ensure_glossary_term(
        self, glossary: str, name: str, display_name: str, description: str
    ) -> str:
        payload = {
            "name": name,
            "glossary": glossary,
            "displayName": display_name,
            "description": description,
        }
        resp = await self._put(f"{self.base_url}/api/v1/glossaryTerms", payload)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("fullyQualifiedName") or f"{glossary}.{name}")

    async def ensure_domain(self, name: str, description: str = "") -> str:
        payload = {"name": name, "domainType": "Source-aligned", "description": description}
        resp = await self._put(f"{self.base_url}/api/v1/domains", payload)
        resp.raise_for_status()
        data = resp.json()
        return str(data["id"])

    async def get_domain_id(self, domain_name: str) -> str | None:
        url = f"{self.base_url}/api/v1/domains/name/{quote(domain_name, safe='')}"
        resp = await self._get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return str(resp.json()["id"])

    async def _resolve_property_type_id(self, type_name: str = "string") -> str | None:
        url = f"{self.base_url}/api/v1/metadata/types?category=field&limit=100"
        resp = await self._get(url)
        if resp.status_code != 200:
            return None
        for entry in resp.json().get("data", []):
            if entry.get("name", "").lower() == type_name.lower():
                return str(entry["id"])
        return None

    async def register_table_custom_property(self, prop_name: str, prop_description: str) -> None:
        url = f"{self.base_url}/api/v1/metadata/types/name/table"
        resp = await self._get(url)
        resp.raise_for_status()
        payload = resp.json()
        custom_properties: list[dict[str, Any]] = payload.get("customProperties") or []
        if any(prop.get("name") == prop_name for prop in custom_properties):
            return

        type_id = await self._resolve_property_type_id("markdown")
        if type_id is None:
            type_id = await self._resolve_property_type_id("string")
        if type_id is None:
            logger.warning(
                "Could not resolve propertyType UUID for %s — skipping custom property registration",
                prop_name,
            )
            return

        custom_properties.append(
            {
                "name": prop_name,
                "description": prop_description,
                "propertyType": {"id": type_id, "type": "type"},
            }
        )
        payload["customProperties"] = custom_properties
        put_resp = await self._put(url, payload)
        put_resp.raise_for_status()

    async def ensure_governance_taxonomy(self) -> None:
        """Bootstrap fixed governance taxonomy in OpenMetadata.

        Creates classifications, tags, glossary, and custom property required
        for Phase II governance enrichment. All calls are idempotent (PUT).
        Each step is best-effort: a failure logs a warning but does not abort
        the rest of the bootstrap or the enrichment run.
        """
        steps: list[tuple[str, Any]] = [
            (
                "PIIType classification",
                self.ensure_classification(
                    "PIIType",
                    "Granular PII classifications inferred by the ARTOO enricher.",
                    mutually_exclusive=True,
                ),
            ),
        ]
        # Run classification first so tags can reference it
        for label, coro in steps:
            try:
                await coro
            except Exception as exc:
                logger.warning("Taxonomy bootstrap step failed (%s): %s", label, exc)

        for name, description in {
            "Name": "Personal name (first, last, full)",
            "Email": "Email address",
            "Phone": "Phone or mobile number",
            "DateOfBirth": "Date of birth",
            "NationalID": "National identity document, passport, or tax ID",
        }.items():
            try:
                await self.ensure_tag("PIIType", name, description)
            except Exception as exc:
                logger.warning("Taxonomy bootstrap step failed (PIIType.%s): %s", name, exc)

        try:
            await self.ensure_classification(
                "DataSensitivity",
                "Column-level sensitivity inferred by the ARTOO enricher.",
                mutually_exclusive=True,
            )
        except Exception as exc:
            logger.warning(
                "Taxonomy bootstrap step failed (DataSensitivity classification): %s", exc
            )

        for name, description in {
            "Public": "Can be shared externally without restriction",
            "Internal": "For internal use; no customer-facing exposure",
            "Confidential": "Restricted to authorized personnel; contains business-sensitive data",
            "Restricted": "Highest sensitivity; direct identifiers, secrets, credentials, or regulated data",
        }.items():
            try:
                await self.ensure_tag("DataSensitivity", name, description)
            except Exception as exc:
                logger.warning("Taxonomy bootstrap step failed (DataSensitivity.%s): %s", name, exc)

        try:
            await self.ensure_classification(
                "Tier",
                "Table criticality tier inferred by the ARTOO enricher.",
                mutually_exclusive=True,
            )
        except Exception as exc:
            logger.warning("Taxonomy bootstrap step failed (Tier classification): %s", exc)

        for name, description in {
            "Tier1": "Core transactional tables with highest business criticality",
            "Tier2": "Important reference tables frequently joined by other entities",
            "Tier3": "Analytical or aggregate tables used for reporting",
            "Tier4": "Auxiliary or supporting tables such as lookup codes",
            "Tier5": "Staging, temporary, or deprecated tables",
        }.items():
            try:
                await self.ensure_tag("Tier", name, description)
            except Exception as exc:
                logger.warning("Taxonomy bootstrap step failed (Tier.%s): %s", name, exc)

        try:
            await self.ensure_classification(
                "Business",
                "Business domain tags inferred by the ARTOO enricher.",
                mutually_exclusive=False,
            )
        except Exception as exc:
            logger.warning("Taxonomy bootstrap step failed (Business classification): %s", exc)

        try:
            await self.ensure_glossary(
                "BusinessTerms",
                "Business Terms",
                "Auto-generated business vocabulary from the ARTOO semantic enricher.",
            )
        except Exception as exc:
            logger.warning("Taxonomy bootstrap step failed (BusinessTerms glossary): %s", exc)

        try:
            await self.register_table_custom_property(
                "commonQueries",
                "Typical natural-language questions this table can answer, inferred by the ARTOO enricher.",
            )
        except Exception as exc:
            logger.warning(
                "Taxonomy bootstrap step failed (commonQueries custom property): %s", exc
            )

    async def close(self) -> None:
        await self._client.aclose()


async def get_default_client() -> OpenMetadataClient:
    base_url = str(settings.openmetadata_url).rstrip("/")
    token = settings.openmetadata_api_token or await _login_token(base_url)
    return OpenMetadataClient(base_url, token)


__all__ = ["OpenMetadataClient", "get_default_client"]
