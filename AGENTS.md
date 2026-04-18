# AGENTS.md

## Repo Shape
- `src/artoo/` — all application code.
- `src/artoo/api/server.py` — FastAPI entrypoint (mounts MCP at `/mcp` and static chat UI at `/`).
- `src/artoo/enricher/__main__.py` — CLI entrypoint: `--bootstrap-only` registers the OM connector; default mode runs governance taxonomy bootstrap then semantic enrichment.
- `src/artoo/config.py` — single `Settings` (pydantic-settings, `extra="ignore"`) loaded at module level as `settings`. Env files: `.env.local` first, then `.env`.
- `openmetadata/` — bootstrap/crawl helper scripts consumed by the Makefile.
- `postgres/seed.py` — demo data seeder, run inside the `artoo-api` container by `make seed`.
- `tests/` — pytest suite (4 test files, 37 tests). No integration-test infrastructure; all tests are plain unit tests.

## Commands
- **Always use `uv`, never `pip`.**
- `make lint` — `ruff check . --fix && ruff format . && mypy src/`
- `make test` — `uv run pytest -m unit --cov=src/artoo`
- `make down` — tears down containers + volumes; may need `sudo rm -rf docker-volume/db-data-postgres` on permission failure.
- `make demo` — full local stack: `up` → `seed` → `bootstrap` → `crawl` → `api`.
- `make demo-full` — same as `demo` but adds `enrich` before `api`.
- `make seed DEMO_PROFILE=ecommerce` — loads the ecommerce demo from `demos/ecommerce/`; `DEMO_PROFILE` is read from `.env.local` if present.

## Testing — Important Gotcha
- **`make test` currently selects zero tests** because it filters with `-m unit` but no test file applies `@pytest.mark.unit`. To actually run the suite: `uv run python -m pytest` (or `uv run python -m pytest --cov=src/artoo`).
- `uv run pytest` also fails because `pytest` is not installed as a direct script — always use `uv run python -m pytest`.
- Async tests use `@pytest.mark.asyncio`; `conftest.py` provides a session-scoped `event_loop`.
- `conftest.py` strips non-Settings env vars before collection so the local `.env.local` (which contains Docker/Airflow vars) doesn't cause pydantic validation errors.
- Tests mock external services (OpenMetadata, LLM, asyncpg) in-process; no Docker or network needed.

## Lint & Type-Check
- Ruff: line-length 100, import sorting enabled (`extend-select = ["I"]`).
- mypy: strict mode, `ignore_missing_imports = false` — every import needs type stubs or an explicit `# type: ignore`. `asyncpg` has no stubs; annotate its import with `# type: ignore[import-untyped]`.
- Pre-commit hooks: `ruff`, `ruff-format`, `mypy`, and Prettier (only for `src/artoo/chat/*.html`).

## Configuration
- Settings load from `.env.local` then `.env` (pydantic-settings `SettingsConfigDict`, `extra="ignore"`).
- Extra env vars (AWS keys, Airflow, Superset) in `.env.local` are silently ignored by `Settings` — this is intentional.
- Default LLM provider is `bedrock` (model `eu.amazon.nova-lite-v1:0`, region `eu-south-2`). Alternatives: `anthropic`, `openai`.
- Docker containers need explicit `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`; SSO profiles don't work inside containers — keep `LLM_AWS_PROFILE` empty.
- Default Postgres DSN uses the Compose service name `postgresql` (not `localhost`).
- `OPENMETADATA_DB_FILTER` — optional FQN prefix (e.g. `my-service.my_db`) that scopes `list_tables` and `get_table_id` to a specific database. Unset means all tables.
- Chat requests now route by intent: conversational questions get a direct reply, while data queries go through schema context → SQL generation → EXPLAIN dry-run → execution.
- Keep prompts and docs generic. Do not bake domain-specific relationship rules into the SQL prompt; rely on the schema context, foreign keys, and table descriptions instead.

## Enricher — Phase II Governance
The enricher now runs a two-step flow:

1. **Taxonomy bootstrap** (`ensure_governance_taxonomy()`) — idempotent, best-effort. Creates:
   - Classification `PIIType` with tags: `Name`, `Email`, `Phone`, `DateOfBirth`, `NationalID`
   - Classification `DataSensitivity` with tags: `Public`, `Internal`, `Confidential`, `Restricted`
   - Glossary `BusinessTerms`
   - Custom property `commonQueries` on the `table` entity (resolves `propertyType` UUID dynamically via `GET /api/v1/metadata/types`)

2. **Per-table enrichment** — for each table the writer applies (all best-effort):
   - Column descriptions + display names (Phase I, unchanged)
   - `PII.Sensitive` tag for any PII column, even if `pii_type` is null
   - `PIIType.*` tag when `pii_type` is non-null
   - `DataSensitivity.*` tag on every column
   - `Tier.Tier{1-5}` + `Business.*` tags on the table
   - Domain assignment (on-demand creation; `business_domain` is normalized: `customer_ops` → `Customer Ops`)
   - `commonQueries` stored in the table's `extension` field
   - Glossary term per unique `business_name`; dedup tracked across the full run in `CatalogWriter._seen_glossary_terms`

## Docker
- Single multi-stage `Dockerfile` with named targets: `enricher` and `api`.
- `docker-compose.yml` and the Makefile are the source of truth for local orchestration; prefer them over ad-hoc `docker run`.
- `make crawl` bypasses Airflow intentionally (incompatible plugin); it execs `metadata ingest` directly in the `openmetadata_ingestion` container.
- OpenMetadata is slow on first boot (3–5 min); `make bootstrap` polls up to 30 attempts.
- The demo Postgres image already ships a base init script that creates the OpenMetadata database/user; demo profile init scripts should only create the app demo roles/tables.
- `demos/ecommerce/seed.py` must stay aligned with the ecommerce schema in `demos/ecommerce/init.sh`.

## API Endpoints
`POST /api/query` · `GET /api/tables` · `GET /api/table/{fqn}` · `GET /health` · `/mcp`
