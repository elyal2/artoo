from __future__ import annotations

import asyncio
import logging
import os

import httpx

from artoo.config import settings
from artoo.logging import configure_logging

logger = logging.getLogger(__name__)

BOOTSTRAP_ADMIN_TOKEN = os.environ.get("OPENMETADATA_BOOTSTRAP_TOKEN", "ingestion-bot")


async def wait_for_health(url: str) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        for _ in range(60):
            try:
                resp = await client.get(f"{url}/api/v1/system/version")
                if resp.status_code == 200:
                    logger.info("OpenMetadata healthy")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
    raise RuntimeError("OpenMetadata not healthy after timeout")


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = settings.openmetadata_api_token or BOOTSTRAP_ADMIN_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def ensure_postgres_service(client: httpx.AsyncClient) -> str:
    pg_password = os.environ.get("POSTGRES_PASSWORD", "artoo_demo")
    payload = {
        "name": "hotel-demo-postgres",
        "serviceType": "Postgres",
        "connection": {
            "config": {
                "type": "Postgres",
                "hostPort": "postgresql:5432",
                "database": "hotel_demo",
                "username": "artoo_demo",
                "password": pg_password,
                "scheme": "postgresql+psycopg2",
            }
        },
    }
    resp = await client.post(
        f"{settings.openmetadata_url}/api/v1/services/databaseServices",
        headers=_auth_headers(),
        json=payload,
    )
    if resp.status_code not in {200, 201, 409}:
        resp.raise_for_status()
    data = resp.json()
    service_id = data.get("id")
    if not service_id:
        existing = await client.get(
            f"{settings.openmetadata_url}/api/v1/services/databaseServices/name/hotel-demo-postgres",
            headers=_auth_headers(),
        )
        existing.raise_for_status()
        service_id = existing.json()["id"]
    return str(service_id)


async def trigger_ingestion(client: httpx.AsyncClient, service_id: str) -> None:
    payload = {
        "name": "hotel-demo-metadata-ingestion",
        "pipelineType": "metadata",
        "service": {"id": service_id},
        "sourceConfig": {
            "config": {
                "type": "DatabaseMetadata",
                "markDeletedTables": True,
                "includeTables": True,
                "includeViews": True,
            }
        },
    }
    resp = await client.post(
        f"{settings.openmetadata_url}/api/v1/services/ingestionPipelines",
        headers=_auth_headers(),
        json=payload,
    )
    if resp.status_code not in {200, 201, 409}:
        resp.raise_for_status()
    data = resp.json()
    pipeline_id = data.get("id")
    if pipeline_id:
        run_resp = await client.post(
            f"{settings.openmetadata_url}/api/v1/services/ingestionPipelines/run/{pipeline_id}",
            headers=_auth_headers(),
        )
        if run_resp.status_code not in {200, 201}:
            logger.warning("Ingestion trigger returned %s", run_resp.status_code)


async def main() -> None:
    configure_logging()
    om_url = str(settings.openmetadata_url)
    await wait_for_health(om_url)
    async with httpx.AsyncClient(timeout=30) as client:
        service_id = await ensure_postgres_service(client)
        await trigger_ingestion(client, service_id)
    logger.info("OpenMetadata bootstrap complete")


if __name__ == "__main__":
    asyncio.run(main())
