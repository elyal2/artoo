#!/usr/bin/env python3
"""Triggers the OpenMetadata ingestion crawl, waiting for Airflow to register the DAG."""

from __future__ import annotations

import asyncio
import base64
import logging
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OM_URL = "http://localhost:8585"
MAX_ATTEMPTS = 24
WAIT_SECONDS = 10


async def get_token() -> str:
    password = base64.b64encode(b"admin").decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{OM_URL}/api/v1/users/login",
            headers={"Content-Type": "application/json"},
            json={"email": "admin@open-metadata.org", "password": password},
        )
        resp.raise_for_status()
        return str(resp.json()["accessToken"])


async def main() -> None:
    token = await get_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=10) as client:
        # Get pipeline ID
        resp = await client.get(
            f"{OM_URL}/api/v1/services/ingestionPipelines?limit=1",
            headers=headers,
        )
        resp.raise_for_status()
        pipelines = resp.json().get("data", [])
        if not pipelines:
            logger.error("No ingestion pipelines found. Run 'make bootstrap' first.")
            sys.exit(1)

        pipeline_id = pipelines[0]["id"]
        pipeline_name = pipelines[0]["name"]
        logger.info(f"Found pipeline: {pipeline_name} ({pipeline_id})")

        # Wait for Airflow to register the DAG, then trigger run
        for attempt in range(1, MAX_ATTEMPTS + 1):
            run_resp = await client.post(
                f"{OM_URL}/api/v1/services/ingestionPipelines/run/{pipeline_id}",
                headers=headers,
            )
            if run_resp.status_code in {200, 201}:
                logger.info("Crawl triggered successfully.")
                return
            logger.info(
                f"Attempt {attempt}/{MAX_ATTEMPTS} — DAG not ready in Airflow yet, "
                f"waiting {WAIT_SECONDS}s..."
            )
            await asyncio.sleep(WAIT_SECONDS)

    logger.warning(
        "Could not trigger crawl automatically. "
        "Trigger manually from Airflow UI: http://localhost:8080"
    )


if __name__ == "__main__":
    asyncio.run(main())
