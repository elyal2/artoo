.PHONY: up down seed enrich api bootstrap crawl demo demo-full _demo-banner logs ps help test lint

COMPOSE_FILES=-f docker-compose.yml

# Local DSN to seed from host; override if needed
POSTGRES_DSN_LOCAL ?= postgresql://artoo_demo:artoo_demo@localhost:5432/hotel_demo

help:
	@echo "make up        - levanta stack OM + overrides"
	@echo "make seed      - carga datos demo hotel_demo (usa POSTGRES_DSN_LOCAL)"
	@echo "make bootstrap - registra el conector PostgreSQL en OpenMetadata y dispara crawl"
	@echo "make enrich    - ejecuta artoo-enricher (enriquecimiento semántico)"
	@echo "make api       - levanta artoo-api"
	@echo "make demo      - up + seed + bootstrap + api (sin enrich: ejecútalo en vivo)"
	@echo "make demo-full - up + seed + bootstrap + enrich + api (todo automático)"
	@echo "make logs      - tail logs"
	@echo "make ps        - estado contenedores"
	@echo "make test      - tests unitarios"
	@echo "make lint      - ruff check + format + mypy"
	@echo "make down      - baja todo y volúmenes"

up:
	docker compose $(COMPOSE_FILES) build artoo-api artoo-enricher superset
	docker compose $(COMPOSE_FILES) up -d

ps:
	docker compose $(COMPOSE_FILES) ps

logs:
	docker compose $(COMPOSE_FILES) logs -f

seed:
	docker compose $(COMPOSE_FILES) build artoo-api
	docker compose $(COMPOSE_FILES) up -d postgresql
	@echo "Waiting for PostgreSQL..."
	@sleep 3
	docker compose $(COMPOSE_FILES) run --rm artoo-api uv run python postgres/seed.py

bootstrap:
	docker compose $(COMPOSE_FILES) build artoo-enricher
	@echo "Waiting for OpenMetadata to be healthy..."
	@for i in $$(seq 1 30); do \
		curl -sf http://localhost:8585/api/v1/system/version > /dev/null && break; \
		echo "Attempt $$i/30 - OM not ready..."; sleep 5; \
	done
	docker compose $(COMPOSE_FILES) run --rm artoo-enricher uv run python -m artoo.enricher --bootstrap-only

crawl:
	@echo "Running metadata ingestion directly via CLI (bypassing Airflow)..."
	@TOKEN=$$(curl -sf -X POST http://localhost:8585/api/v1/users/login \
		-H 'Content-Type: application/json' \
		-d '{"email":"admin@open-metadata.org","password":"YWRtaW4="}' \
		| python3 -c 'import sys,json; print(json.load(sys.stdin)["accessToken"])') && \
	docker exec \
		-e OPENMETADATA_INGEST_TOKEN=$$TOKEN \
		-e ARTOO_DB_PASSWORD=$${ARTOO_DB_PASSWORD:-artoo_demo} \
		openmetadata_ingestion \
		bash -c 'envsubst < /opt/openmetadata/ingest.yaml > /tmp/ingest.yaml && metadata ingest -c /tmp/ingest.yaml'

enrich:
	docker compose $(COMPOSE_FILES) build artoo-enricher
	docker compose $(COMPOSE_FILES) run --rm artoo-enricher

api:
	docker compose $(COMPOSE_FILES) up -d artoo-api

test:
	uv run pytest -m unit --cov=src/artoo

lint:
	uv run ruff check . --fix
	uv run ruff format .
	uv run mypy src/

demo: up seed bootstrap crawl api
	@$(MAKE) _demo-banner

demo-full: up seed bootstrap crawl enrich api
	@$(MAKE) _demo-banner

_demo-banner:
	@echo ""
	@echo "╔══════════════════════════════════════════╗"
	@echo "║  ARTOO Demo Ready!                       ║"
	@echo "║  Chat:           http://localhost:8000   ║"
	@echo "║  OpenMetadata:   http://localhost:8585   ║"
	@echo "║  Superset:       http://localhost:8088   ║"
	@echo "║  PostgreSQL:     localhost:5432        ║"
	@echo "╚══════════════════════════════════════════╝"

down:
	docker compose $(COMPOSE_FILES) down -v --remove-orphans
	@docker run --rm -v "$(PWD)/docker-volume:/data" --user root alpine \
		sh -c "rm -rf /data/db-data-postgres" 2>/dev/null && echo "Cleaned db-data-postgres" || \
		echo "⚠️  Could not remove docker-volume/db-data-postgres — run: sudo rm -rf docker-volume/db-data-postgres"