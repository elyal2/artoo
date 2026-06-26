from __future__ import annotations

import asyncio
import asyncpg
import base64
import logging
import os

import httpx

from artoo.config import settings
from artoo.logging import configure_logging

logger = logging.getLogger(__name__)


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


async def get_jwt_token(url: str) -> str:
    """Login as admin and return a JWT token."""
    # Per OM docs: password must be base64-encoded
    password = base64.b64encode(b"admin").decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{url}/api/v1/users/login",
            headers={"Content-Type": "application/json"},
            json={"email": "admin@open-metadata.org", "password": password},
        )
        resp.raise_for_status()
        token = resp.json().get("accessToken")
        if not token:
            raise RuntimeError(f"No accessToken in login response: {resp.json()}")
        logger.info("Obtained JWT token from OpenMetadata admin login")
        return str(token)


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


async def ensure_postgres_service(client: httpx.AsyncClient, om_url: str, token: str) -> str:
    from artoo.config import _extract_db_name

    pg_password = os.environ.get("ARTOO_DB_PASSWORD", "artoo_demo")
    service_name = settings.openmetadata_service_name
    database_name = _extract_db_name(settings.postgres_dsn)
    payload = {
        "name": service_name,
        "serviceType": "Postgres",
        "connection": {
            "config": {
                "type": "Postgres",
                "hostPort": "postgresql:5432",
                "database": database_name,
                "username": "artoo_demo",
                "authType": {"password": pg_password},
            }
        },
    }
    resp = await client.post(
        f"{om_url}/api/v1/services/databaseServices",
        headers=_auth_headers(token),
        json=payload,
    )
    if resp.status_code not in {200, 201, 409}:
        resp.raise_for_status()
    data = resp.json()
    service_id = data.get("id")
    if not service_id:
        existing = await client.get(
            f"{om_url}/api/v1/services/databaseServices/name/{service_name}",
            headers=_auth_headers(token),
        )
        existing.raise_for_status()
        service_id = existing.json()["id"]
    return str(service_id)


async def trigger_ingestion(
    client: httpx.AsyncClient, om_url: str, token: str, service_id: str
) -> None:

    service_name = settings.openmetadata_service_name
    payload = {
        "name": f"{service_name}-metadata-ingestion",
        "pipelineType": "metadata",
        "service": {"id": service_id, "type": "databaseService"},
        "airflowConfig": {
            "scheduleInterval": "0 * * * *",
        },
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
        f"{om_url}/api/v1/services/ingestionPipelines",
        headers=_auth_headers(token),
        json=payload,
    )
    if resp.status_code not in {200, 201, 409}:
        resp.raise_for_status()
    data = resp.json()
    pipeline_id = data.get("id")
    if pipeline_id:
        # Deploy the pipeline to Airflow first, then trigger the run
        deploy_resp = await client.post(
            f"{om_url}/api/v1/services/ingestionPipelines/deploy/{pipeline_id}",
            headers=_auth_headers(token),
        )
        if deploy_resp.status_code not in {200, 201}:
            logger.warning("Pipeline deploy returned %s", deploy_resp.status_code)
            return
        logger.info("Pipeline deployed to Airflow")
        # Give Airflow a few seconds to register the DAG
        await asyncio.sleep(10)
        run_resp = await client.post(
            f"{om_url}/api/v1/services/ingestionPipelines/run/{pipeline_id}",
            headers=_auth_headers(token),
        )
        if run_resp.status_code not in {200, 201}:
            logger.warning(
                "Ingestion trigger returned %s — run it manually from Airflow UI (http://localhost:8080)",
                run_resp.status_code,
            )
        else:
            logger.info("Ingestion pipeline triggered successfully")


async def ensure_airflow_db() -> None:
    """Create Airflow database and user if they don't exist."""
    airflow_user = os.getenv("AIRFLOW_DB_USER", "airflow_user")
    airflow_pass = os.getenv("AIRFLOW_DB_PASSWORD", "airflow_pass")
    airflow_db = os.getenv("AIRFLOW_DB", "airflow_db")
    
    # Connect as postgres superuser
    postgres_dsn = str(settings.postgres_dsn).replace("+psycopg2", "")
    # Replace database name with 'postgres' to connect to default DB
    postgres_dsn = postgres_dsn.rsplit("/", 1)[0] + "/postgres"
    # Replace user with postgres
    postgres_dsn = postgres_dsn.replace("artoo_demo:artoo_demo", "postgres:openmetadata_default")
    
    try:
        conn = await asyncpg.connect(postgres_dsn)
        
        # Check if user exists
        user_exists = await conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", airflow_user
        )
        
        if not user_exists:
            logger.info(f"Creating Airflow user: {airflow_user}")
            await conn.execute(
                f"CREATE ROLE {airflow_user} LOGIN PASSWORD '{airflow_pass}'"
            )
        
        # Check if database exists
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", airflow_db
        )
        
        if not db_exists:
            logger.info(f"Creating Airflow database: {airflow_db}")
            await conn.execute(
                f"CREATE DATABASE {airflow_db} OWNER {airflow_user}"
            )
            await conn.execute(
                f"GRANT ALL PRIVILEGES ON DATABASE {airflow_db} TO {airflow_user}"
            )
        
        await conn.close()
        logger.info("Airflow database setup complete")
    except Exception as e:
        logger.warning(f"Could not ensure Airflow DB (may already exist): {e}")


async def main() -> None:
    configure_logging()
    om_url = str(settings.openmetadata_url).rstrip("/")
    
    # Ensure Airflow DB exists (idempotent)
    await ensure_airflow_db()
    
    await wait_for_health(om_url)
    token = await get_jwt_token(om_url)
    async with httpx.AsyncClient(timeout=30) as client:
        service_id = await ensure_postgres_service(client, om_url, token)
        await trigger_ingestion(client, om_url, token, service_id)
    logger.info("OpenMetadata bootstrap complete")


if __name__ == "__main__":
    asyncio.run(main())
