import asyncio
import os

import pytest

# ---------------------------------------------------------------------------
# Isolate tests from the local .env.local / .env files so that extra Docker
# variables (aws_access_key_id, airflow_admin_password, …) don't cause
# pydantic-settings to reject the Settings object with extra_forbidden.
# ---------------------------------------------------------------------------

# Strip any env vars that Settings does not declare before importing anything
# from artoo (which instantiates Settings at module level).
_ALLOWED_SETTINGS_VARS = {
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_CHART_MODEL",
    "LLM_CHART_MAX_TOKENS",
    "LLM_API_KEY",
    "LLM_AWS_PROFILE",
    "LLM_AWS_REGION",
    "LLM_MAX_TOKENS",
    "LLM_TEMPERATURE",
    "DEMO_PROFILE",
    "POSTGRES_DSN",
    "POSTGRES_PASSWORD",
    "OPENMETADATA_URL",
    "OPENMETADATA_API_TOKEN",
    "OPENMETADATA_SERVICE_NAME",
    "OPENMETADATA_DB_FILTER",
    "API_PORT",
    "QUERY_TIMEOUT_SECONDS",
    "MAX_RESULT_ROWS",
    "SAMPLE_ROWS",
    "ENRICHMENT_CONCURRENCY",
    "LOG_LEVEL",
    "LOG_FORMAT",
}

for _key in list(os.environ):
    if _key.upper() not in _ALLOWED_SETTINGS_VARS:
        os.environ.pop(_key, None)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
