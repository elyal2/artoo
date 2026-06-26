# AGENTS.md

## Repo Shape
- `src/artoo/` — all application code.
- `src/artoo/api/server.py` — FastAPI entrypoint; mounts MCP at `/mcp`, static chat UI at `/`, adds `NoCacheStaticMiddleware` for all non-API paths.
- `src/artoo/enricher/__main__.py` — CLI: `--bootstrap-only` registers the OM connector; default mode runs taxonomy bootstrap then per-table semantic enrichment.
- `src/artoo/config.py` — single `Settings` (pydantic-settings, `extra="ignore"`) instantiated at module level as `settings`. Loaded at import time — cannot be patched after import without reloading.
- `openmetadata/` — bootstrap/crawl helper scripts consumed by the Makefile only; not importable app code.
- `demos/<profile>/` — each profile has `init.sh` (Postgres init, mounted as `02-init.sh`) and `seed.py` run inside the container. Available profiles: `hotel` (default), `ecommerce`, `andorra`.
- `tests/` — 46 pure unit tests; no Docker or network required.

## Commands
- **Always `uv`, never `pip`.**
- Run tests: `uv run python -m pytest` — `uv run pytest` fails (pytest is not a direct script).
- Run tests with coverage: `uv run python -m pytest --cov=src/artoo`
- Lint + typecheck: `make lint` → `ruff check . --fix && ruff format . && mypy src/`
- **`make test` runs zero tests** — passes `-m unit` but no test uses `@pytest.mark.unit`. Use `uv run python -m pytest` directly.

## Docker / Demo Commands
- `make demo` = `restart` → `seed` → `bootstrap` → `crawl` → `api` (order matters, do not skip).
- `make demo-full` = same + `enrich` before `api`.
- `make seed DEMO_PROFILE=ecommerce` — `DEMO_PROFILE` also read from `.env.local` if set.
- `make bootstrap` polls OM health up to 30 × 5 s; OM takes 3–5 min on first boot.
- `make crawl` bypasses Airflow (incompatible plugin); runs `metadata ingest` directly inside `openmetadata_ingestion` via `docker exec`.
- `make down` may need `sudo rm -rf docker-volume/db-data-postgres` on permission failure.
- `artoo-enricher` has `profiles: [tools]` in Compose — not started by plain `docker compose up`; use `docker compose run --rm artoo-enricher` or `make enrich`.

## Testing Quirks
- `conftest.py` strips all env vars not in `_ALLOWED_SETTINGS_VARS` before collection — prevents `.env.local` Docker/Airflow vars from crashing `Settings()` at import time.
- `event_loop` fixture is session-scoped; required for shared async state across tests.
- All external services (OpenMetadata, LLM, asyncpg) are mocked in-process; no containers needed for tests.

## Lint & Type-Check
- Ruff: line-length **100**, import sorting via `extend-select = ["I"]`.
- mypy: strict, `ignore_missing_imports = false` — every third-party import needs stubs or `# type: ignore`. `asyncpg` has no stubs → `# type: ignore[import-untyped]`.
- Pre-commit: `ruff`, `ruff-format`, `mypy`, Prettier (Prettier runs only on `src/artoo/chat/*.html`).

## Configuration
- Env load order: `.env.local` first, then `.env`. Extra vars silently ignored (`extra="ignore"`).
- Default Postgres DSN uses Compose service name `postgresql` (not `localhost`).
- Default OM URL uses Compose service name `openmetadata-server:8585` (not `localhost`).
- Default LLM: `bedrock`, model `eu.amazon.nova-lite-v1:0`, region `eu-south-2`.
- **Bedrock EU regions require `eu.` prefix** in model IDs: `eu.amazon.nova-lite-v1:0`, `eu.anthropic.claude-sonnet-4-20250514-v1:0`. Without prefix → `ValidationException: inference profile required`.
- **Docker config cache**: `Settings` loads once at import time. Restart alone won't reload env vars — use `docker compose stop <svc> && docker compose rm -f <svc> && docker compose up -d <svc>`.
- `LLM_AWS_PROFILE` must be **empty** in Docker — SSO unavailable in containers; use `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`.
- `LLM_INTENT_MODEL` — separate optional model for intent classification; recommend a more capable model than `LLM_MODEL` to correctly classify hypothetical/scenario questions as `data_query`. Falls back to `LLM_MODEL` if unset.
- `LLM_EXPLANATION_MODEL` — separate optional model for result interpretation; recommend a more capable model for better unit context. Falls back to `LLM_MODEL` if unset.
- `LLM_CHART_MODEL` — separate optional model for D3 chart generation; recommend a more capable model than `LLM_MODEL` (e.g. Claude Sonnet). Falls back to `LLM_MODEL` if unset.
- `ENRICHMENT_LLM_MODEL` — separate optional model for enricher; can use cheaper model (Nova Lite) for cost savings. Falls back to `LLM_MODEL` if unset.
- `OPENMETADATA_DB_FILTER` — FQN prefix to scope `list_tables`/`get_table_id` to a specific DB. Unset = all tables.

## Query Pipeline
Intent routing in `pipeline.py`: every request is classified first (`conversational` | `data_query`). Conversational replies return `QueryResponse` with no `sql` field — the frontend checks `!data.sql` to render plain text.

SQL path: schema context → LLM SQL generation → `sqlglot` AST column validation (fail-open for unqualified refs) → `EXPLAIN` dry-run → execute. One retry with error feedback on failure.

Keep all LLM prompts domain-agnostic — no hardcoded business rules. Rely entirely on schema context, column descriptions, and FK relationships from OpenMetadata.

## API Endpoints
`POST /api/query` · `GET /api/tables` · `GET /api/table/{fqn}` · `GET /health` · `/mcp`

Static files served from `src/artoo/chat/` at `/` with `no-cache` headers on every response.

## Enricher — Governance Flow
Two-step, idempotent:

1. **Taxonomy bootstrap** (`ensure_governance_taxonomy()`): creates `PIIType` classification (Name, Email, Phone, DateOfBirth, NationalID), `DataSensitivity` classification (Public, Internal, Confidential, Restricted), `BusinessTerms` glossary, `UnidadesMedida` glossary (Millones_EUR, Miles_EUR, Euros, Porcentaje_0_100, Ratio_Decimal, Dias, Unidades_Fisicas), `commonQueries` custom property on `table` entity (UUID resolved dynamically via `GET /api/v1/metadata/types`).

2. **Per-table enrichment** (all best-effort): column descriptions + display names; `PII.Sensitive` tag for any PII column; `PIIType.*` tag when `pii_type` non-null; `DataSensitivity.*` on every column; `Tier.Tier{1-5}` + `Business.*` on the table; domain assignment (`business_domain` normalized: `customer_ops` → `Customer Ops`); `commonQueries` in `extension`; glossary term per unique `business_name` (dedup in `CatalogWriter._seen_glossary_terms` across full run); unit detection via regex patterns → `UnidadesMedida.*` tags on columns with numeric units.

3. **Unit enrichment post-processor**: `_enrich_unit_descriptions()` detects 83 unit patterns (monetary: millones/miles/k, percentages, time, counts, weights, volumes, finance bps) and enhances column descriptions with explicit unit context. Post-processor uses word boundaries to avoid false positives.

## Docker / Postgres Init
- Multi-stage `Dockerfile`: named targets `enricher` and `api`.
- Base Postgres image already creates OM db/user (`postgres-script.sql`); demo `init.sh` must **only** add demo-specific roles/tables — never recreate `openmetadata_user` or `openmetadata_db`.
- `demos/ecommerce/seed.py` must stay in sync with `demos/ecommerce/init.sh`.
- OpenMetadata 1.5.8 API: use `?fields=columns,tableConstraints,usageSummary,tags` (removed `domains` field from 1.2.4, changed to singular `domain` but not used).
