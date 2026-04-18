#!/bin/bash
set -euo pipefail

# Create the OpenMetadata database and user — required by the OM server
# and migration containers. This runs BEFORE the demo profile init script
# (02-init.sh) because of the filename ordering.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE ROLE openmetadata_user LOGIN PASSWORD 'openmetadata_password';
    CREATE DATABASE openmetadata_db OWNER openmetadata_user;
SQL
