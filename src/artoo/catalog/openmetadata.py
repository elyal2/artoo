from __future__ import annotations

import logging
from typing import Any, Iterable, List
from urllib.parse import quote

import httpx

from ..config import settings
from ..models import ColumnMeta, TableDetail, TableSummary

logger = logging.getLogger(__name__)


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

    async def list_tables(self) -> List[TableSummary]:
        all_items: list[TableSummary] = []
        after: str | None = None
        while True:
            url = f"{self.base_url}/api/v1/tables?fields=description,usageSummary&limit=100"
            if after:
                url += f"&after={quote(after, safe='')}"
            resp = await self._client.get(url, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
            for item in data:
                tags = item.get("tags") or [{}]
                all_items.append(
                    TableSummary(
                        name=item.get("fullyQualifiedName", item.get("name")),
                        description=item.get("description"),
                        business_domain=tags[0].get("tagFQN") if tags and tags[0] else None,
                    )
                )
            paging = payload.get("paging", {})
            after = paging.get("after")
            if not after:
                break
        return all_items

    async def get_table(self, fqn: str) -> TableDetail:
        url = f"{self.base_url}/api/v1/tables/name/{fqn}?fields=columns,tableConstraints,usageSummary,owner"
        resp = await self._client.get(url, headers=self._headers())
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
        tags = raw.get("tags") or [{}]
        business_domain = tags[0].get("tagFQN") if tags and tags[0] else None
        return TableDetail(
            name=raw.get("fullyQualifiedName", raw.get("name")),
            description=raw.get("description"),
            business_domain=business_domain,
            columns=cols,
            foreign_keys=[fk for fk in (self._fk_name(c) for c in raw.get("columns", [])) if fk],
        )

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
        resp = await self._client.get(url, headers=self._headers())
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

    async def patch_table(self, fqn: str, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/api/v1/tables/name/{fqn}"
        resp = await self._client.patch(
            url,
            headers={**self._headers(), "Content-Type": "application/json-patch+json"},
            json=payload,
        )
        resp.raise_for_status()

    async def patch_column(self, fqn: str, column: str, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/api/v1/tables/name/{fqn}/columns/{column}"
        resp = await self._client.patch(
            url,
            headers={**self._headers(), "Content-Type": "application/json-patch+json"},
            json=payload,
        )
        resp.raise_for_status()

    async def put_table_tags(self, fqn: str, tags: list[str]) -> None:
        tag_payloads = [{"tagFQN": t} for t in tags]
        payload = (
            [
                {"op": "add", "path": "/tags/-", "value": tag_payloads[0]},
            ]
            if len(tag_payloads) == 1
            else [
                {"op": "replace", "path": "/tags", "value": tag_payloads},
            ]
        )
        await self.patch_table(fqn, payload)

    async def close(self) -> None:
        await self._client.aclose()


async def get_default_client() -> OpenMetadataClient:
    return OpenMetadataClient(str(settings.openmetadata_url), settings.openmetadata_api_token)


__all__ = ["OpenMetadataClient", "get_default_client"]
