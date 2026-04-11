.PHONY: up down seed enrich api bootstrap demo demo-full _demo-banner logs ps help test lint

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
	docker compose $(COMPOSE_FILES) up -d

ps:
	docker compose $(COMPOSE_FILES) ps

logs:
	docker compose $(COMPOSE_FILES) logs -f

seed:
	docker compose $(COMPOSE_FILES) up -d postgresql
	@echo "Waiting for PostgreSQL..."
	@sleep 3
	docker compose $(COMPOSE_FILES) run --rm artoo-api uv run python postgres/seed.py

bootstrap:
	@echo "Waiting for OpenMetadata to be healthy..."
	@for i in $$(seq 1 30); do \
		curl -sf http://localhost:8585/api/v1/system/version > /dev/null && break; \
		echo "Attempt $$i/30 - OM not ready..."; sleep 5; \
	done
	docker compose $(COMPOSE_FILES) run --rm artoo-enricher uv run python -m artoo.enricher --bootstrap-only

enrich:
	docker compose $(COMPOSE_FILES) run --rm artoo-enricher

api:
	docker compose $(COMPOSE_FILES) up -d artoo-api

test:
	uv run pytest -m unit --cov=src/artoo

lint:
	uv run ruff check . --fix
	uv run ruff format .
	uv run mypy src/

demo: up seed bootstrap api
	@$(MAKE) _demo-banner

demo-full: up seed bootstrap enrich api
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
	docker compose $(COMPOSE_FILES) down -v