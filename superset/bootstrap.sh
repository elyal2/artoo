#!/bin/bash
set -euo pipefail

superset db upgrade

superset fab create-admin \
    --username "${SUPERSET_ADMIN_USER:-admin}" \
    --password "${SUPERSET_ADMIN_PASSWORD:-admin}" \
    --firstname Superset --lastname Admin \
    --email "${SUPERSET_ADMIN_EMAIL:-admin@example.com}" || true

superset init

# Pre-register demo database connection
superset import-datasources -p /app/superset/imports/demo.yaml || \
    echo "WARNING: Could not pre-register demo database (manual setup needed)"
