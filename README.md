# ARTOO

**Catálogo semántico (OpenMetadata) + LLM** — de preguntas en lenguaje natural a SQL fundamentado en el esquema.

El framework es **agnóstico al dominio**: conecta a cualquier base de datos, descubre el esquema, lo enriquece con semántica de negocio vía LLM, y permite consultar en lenguaje natural.

## Requisitos

- **Docker Desktop** (≥ 20.10) con al menos **6 GiB de RAM** asignados
- **Docker Compose** v2
- **Python 3.12+** y [**uv**](https://docs.astral.sh/uv/) (solo para desarrollo local fuera de Docker)
- Credenciales LLM: Bedrock (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`), OpenAI, o Anthropic

## Puesta en marcha

### 1. Configura las variables de entorno

```bash
cp .env.example .env.local
```

Edita `.env.local` y rellena al menos:

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | `bedrock`, `openai` o `anthropic` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Para Bedrock (IAM key) |
| `LLM_AWS_REGION` | Región de Bedrock (ej. `eu-south-2`) |
| `LLM_API_KEY` | Para OpenAI o Anthropic (alternativa a Bedrock) |
| `ARTOO_DB_PASSWORD` | Contraseña del usuario `artoo_demo` en PostgreSQL |
| `OPENMETADATA_DB_FILTER` | *(Opcional)* FQN del servicio/base de datos a enriquecer. Si no se define, procesa todas las tablas. |

> `LLM_AWS_PROFILE` debe quedar vacío cuando se usan `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` — los perfiles SSO no están disponibles dentro de los contenedores Docker.

### 2. Arranca el stack

```bash
make demo
```

Ejecuta en orden:

1. **`up`** — construye imágenes y levanta todos los servicios
2. **`seed`** — carga datos demo en PostgreSQL
3. **`bootstrap`** — registra el servicio PostgreSQL en OpenMetadata y dispara el crawl
4. **`crawl`** — ingesta de metadatos via CLI (sin Airflow)
5. **`api`** — levanta la API ARTOO en http://localhost:8000

> OpenMetadata tarda **3-5 minutos** en estar listo en el primer arranque.

### 3. Enriquece el catálogo

```bash
make enrich
```

El enricher ejecuta dos pasos:

**Bootstrap de taxonomía** (idempotente):
- Clasificaciones `PIIType` y `DataSensitivity`
- Glosario `BusinessTerms`
- Custom property `commonQueries` en el tipo `table`

**Enriquecimiento semántico por tabla**:
- Muestrea filas reales y calcula estadísticas por columna
- Para columnas de baja cardinalidad (≤ 20 valores), el LLM documenta cada código
- Escribe en OpenMetadata: descripciones, tags PII, sensibilidad, tiers, dominios, glosario

Esto permite al chat generar SQL correcto usando los valores codificados reales del esquema.

## URLs

| Servicio | URL | Credenciales |
|---|---|---|
| Chat + API ARTOO | http://localhost:8000 | — |
| OpenMetadata | http://localhost:8585 | `admin` / `admin` |
| Superset | http://localhost:8088 | `admin` / `admin` |
| Airflow | http://localhost:8080 | `admin` / `admin` |

## Makefile

| Comando | Descripción |
|---|---|
| `make demo` | Flujo completo: `up` → `seed` → `bootstrap` → `crawl` → `api` |
| `make demo-full` | Igual que `demo` + `enrich` |
| `make up` | Construye imágenes propias y levanta todos los servicios |
| `make seed` | Carga datos demo en PostgreSQL |
| `make bootstrap` | Registra PostgreSQL en OpenMetadata |
| `make crawl` | Ejecuta el crawl de metadatos via CLI |
| `make enrich` | Enriquecimiento semántico LLM → catálogo |
| `make api` | Levanta `artoo-api` |
| `make test` | Pytest con cobertura |
| `make lint` | Ruff + mypy |
| `make down` | Para servicios y borra todos los volúmenes |

## API

| Endpoint | Descripción |
|---|---|
| `POST /api/query` | `{"question": "..."}` — pregunta en lenguaje natural |
| `POST /api/query` con historial | `{"question": "...", "history": [{"role": "user", "content": "..."}]}` — conversación multi-turno |
| `GET /api/tables` | Lista tablas del catálogo |
| `GET /api/table/{fqn}` | Detalle de una tabla |
| `GET /health` | Estado de la API |
| `/mcp` | Endpoint MCP (`query_data`, `list_tables`, `describe_table`) |

## Chat UI

La interfaz web en http://localhost:8000 ofrece:

- **Entrada en lenguaje natural** — escribe preguntas en texto plano
- **Respuestas conversacionales** — si la pregunta no requiere datos (saludos, preguntas sobre el sistema), responde directamente sin generar SQL
- **Resultados con chart o tabla** — el LLM elige el tipo de gráfico más adecuado (bar, line, bubble, heatmap, donut, etc.) y genera código D3 v7
- **Historial de conversación** — el contexto de preguntas anteriores se mantiene para queries multi-turno
- **Panel de ayuda** — botón `?` en el header que muestra todos los tipos de gráfico disponibles con ejemplos
- **Tema claro/oscuro** — toggle en el header, persistido en localStorage
- **Sidebar con tablas** — lista de tablas disponibles del catálogo con descripción y dominio

## Desarrollo local (sin Docker)

```bash
uv sync --all-extras
uv run python -m pytest          # todos los tests
uv run python -m pytest --cov=src/artoo  # con cobertura
uv run ruff check . --fix
uv run ruff format .
uv run mypy src/
```

## Arquitectura

```
┌─────────────┐    pregunta NL    ┌──────────────────────────────────┐
│  Chat / MCP │ ────────────────► │          artoo-api               │
└─────────────┘                   │  FastAPI + QueryPipeline         │
                                  │  • clasificación de intención    │
                                  │  • contexto semántico de OM      │
                                  │  • LLM genera SQL                │
                                  │  • EXPLAIN dry-run de validación │
                                  │  • asyncpg ejecuta en Postgres   │
                                  └─────────────────────────────────┘
                                             │ lee catálogo
                                  ┌──────────▼───────────────────────┐
                                  │       OpenMetadata               │
                                   │  • tablas, columnas, FKs         │
                                   │  • descripciones + códigos       │
                                   │  • clasificaciones PII           │
                                   │  • sensibilidad por columna      │
                                   │  • tiers, dominios, glosario     │
                                  └──────────▲───────────────────────┘
                                             │ enriquece
                                  ┌──────────┴───────────────────────┐
                                   │       artoo-enricher             │
                                   │  • muestrea filas reales         │
                                   │  • stats por columna             │
                                   │  • LLM infiere semántica         │
                                   │  • documenta códigos exactos     │
                                   │  • PII, sensibilidad, tier       │
                                   │  • dominios y glosario           │
                                  └──────────────────────────────────┘
```

## Notas técnicas

- **Credenciales AWS en Docker**: los perfiles SSO (`~/.aws`) no están disponibles dentro de los contenedores. Usar `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` directamente en `.env.local`.
- **Airflow vs CLI**: el contenedor de ingestion usa Airflow 3.x incompatible con el plugin de OpenMetadata 1.12. `make crawl` ejecuta `metadata ingest` directamente via CLI.
- **Columnas codificadas**: el enricher detecta columnas con ≤ 20 valores distintos y el LLM documenta cada código con su significado de negocio. Crítico para SQL correcto.
- **Governance genérico**: el enricher no asume ningún dominio. Los dominios se infieren del LLM y se crean automáticamente en OpenMetadata. Funciona con cualquier esquema.
- **OpenMetadata login**: `admin` / `admin` (defecto). Si se bloquea la cuenta, esperar ~5 minutos.
- **Superset**: imagen custom basada en `apache/superset:4.1.2` con `psycopg2-binary`. La conexión a la demo se preregistra automáticamente.
- **Volúmenes**: `make down` borra volúmenes Docker y `docker-volume/db-data-postgres/`. Si falla por permisos: `sudo rm -rf docker-volume/db-data-postgres`.

---

© PoC ARTOO — Logicalis España
