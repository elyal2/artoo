# ARTOO (PoC)

Demo técnico: **catálogo semántico (OpenMetadata) + LLM** para pasar de preguntas en lenguaje natural a SQL **fundamentado en el esquema**, con una base PostgreSQL de ejemplo (hotel). Detalle funcional y de arquitectura: [`ARTOO_PoC_Specification.md`](ARTOO_PoC_Specification.md).

## Requisitos

- **Docker Desktop** (≥ 20.10) con al menos **6 GiB de RAM** asignados
- **Docker Compose** v2
- **Python 3.12+** y [**uv**](https://docs.astral.sh/uv/) (solo para desarrollo local fuera de Docker)
- Credenciales para el **LLM** en `.env.local` (AWS Bedrock con perfil SSO, u OpenAI/Anthropic según `LLM_PROVIDER`)

## Puesta en marcha

### 1. Configura las variables de entorno

```bash
cp .env.example .env.local
```

Edita `.env.local` y rellena al menos:

| Variable | Descripción |
|---|---|
| `LLM_AWS_PROFILE` / `LLM_AWS_REGION` | Para Bedrock (SSO) |
| `LLM_API_KEY` | Para OpenAI o Anthropic |
| `POSTGRES_DSN` | DSN de la BD de demo (ya configurado por defecto) |

> Las contraseñas de demo ya tienen valor por defecto en `.env.example`. Cámbialas si el entorno es compartido.

### 2. Arranca el stack completo

```bash
make demo
```

Este comando ejecuta en orden:

1. **`up`** — construye las imágenes propias y levanta todos los servicios (OpenMetadata, OpenSearch, PostgreSQL, Superset, API)
2. **`seed`** — carga ~500 clientes, 6 propiedades, 5.000 reservas y métricas de revenue en `hotel_demo`
3. **`bootstrap`** — espera a que OpenMetadata esté sano, hace login con admin, registra el servicio PostgreSQL y lanza el pipeline de ingestión de metadatos
4. **`api`** — levanta la API ARTOO en http://localhost:8000

> El servidor OpenMetadata tarda **3-5 minutos** en quedar listo en el primer arranque.

### 3. Enriquece el catálogo (opcional antes de la demo)

```bash
make enrich
```

El enricher lee muestras de datos, infiere descripciones y tags con el LLM y los escribe en OpenMetadata. En la demo en vivo se ejecuta **en pantalla** para mostrar el efecto antes/después.

## URLs

| Servicio | URL | Credenciales |
|---|---|---|
| Chat + API ARTOO | http://localhost:8000 | — |
| OpenMetadata | http://localhost:8585 | `admin` / `admin` |
| Superset | http://localhost:8088 | `admin` / `admin` |
| Airflow (ingestión OM) | http://localhost:8080 | `admin` / `admin` |

> Superset arranca con la conexión a `hotel_demo` **ya preconfigurada**. Ve a SQL Lab y empieza a explorar sin configuración adicional.

## Makefile

| Objetivo | Descripción |
|---|---|
| `make demo` | Flujo completo: `up` → `seed` → `bootstrap` → `api` (sin enrich, para hacerlo en directo) |
| `make up` | Construye imágenes propias y levanta todos los servicios |
| `make seed` | Carga datos demo en `hotel_demo` |
| `make bootstrap` | Registra PostgreSQL en OpenMetadata y lanza el crawl de metadatos |
| `make enrich` | Enriquecimiento semántico LLM → catálogo |
| `make api` | Levanta `artoo-api` |
| `make test` | Pytest con cobertura |
| `make lint` | Ruff + mypy |
| `make down` | Para servicios, borra volúmenes Docker y el directorio de datos de PostgreSQL |

## Guion de demo en vivo (~5-7 min)

### Preparación (sin audiencia)

Ejecuta `make demo` la noche anterior o con tiempo. Deja el enrich **sin ejecutar** para mostrar el efecto en directo.

### Narrativa sugerida

1. **"El antes"** — Abre **Superset** (http://localhost:8088): el esquema es críptico (`bkng`, `bk_status`, `cust_tier`…). Responder una pregunta de negocio exige conocer los códigos internos (`CNCL`, `BRZ`, etc.).

2. **Catálogo sin enriquecer** — Abre **OpenMetadata** (http://localhost:8585): el crawler descubrió tablas y columnas pero sin descripciones de negocio útiles. Estructura sí, semántica no.

3. **Enriquecimiento en vivo** — En terminal visible:
   ```bash
   make enrich
   ```
   El enricher lee muestras, llama al LLM y escribe al catálogo en tiempo real.

4. **Catálogo después** — Refresca OpenMetadata: misma tabla (`bkng`) ahora con descripciones, tags de negocio y clasificaciones PII.

5. **"El después" (chat)** — Abre http://localhost:8000 y pregunta en lenguaje natural:
   - *Which properties have the highest cancellation rate?*
   - *Top 10 customers by total spend who haven't returned in 6 months*
   - *Average NPS by property and room category*
   - *Compare weekend vs weekday occupancy across all properties*

**Cierre:** el patrón es **conectar → crawlear → enriquecer → preguntar en natural**. El origen puede ser este PostgreSQL o el del cliente.

## API

| Endpoint | Descripción |
|---|---|
| `POST /api/query` | `{"question": "..."}` — pregunta en lenguaje natural |
| `GET /api/tables` | Lista tablas del catálogo |
| `GET /api/table/{fqn}` | Detalle de una tabla |
| `GET /health` | Estado de la API |
| `/mcp` | Endpoint MCP (herramientas `query_data`, `list_tables`, `describe_table`) |

## Desarrollo local (sin Docker)

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src/
```

## Arquitectura

```
┌─────────────┐    pregunta NL    ┌──────────────────────────────────┐
│  Chat / MCP │ ────────────────► │          artoo-api               │
└─────────────┘                   │  FastAPI + QueryPipeline         │
                                  │  • contexto semántico de OM      │
                                  │  • LLM genera SQL                │
                                  │  • asyncpg ejecuta en Postgres   │
                                  └──────────┬───────────────────────┘
                                             │ lee catálogo
                                  ┌──────────▼───────────────────────┐
                                  │       OpenMetadata               │
                                  │  • tablas, columnas, FKs         │
                                  │  • descripciones (LLM)           │
                                  │  • tags de negocio / PII         │
                                  └──────────▲───────────────────────┘
                                             │ enriquece
                                  ┌──────────┴───────────────────────┐
                                  │       artoo-enricher             │
                                  │  • muestrea filas de Postgres    │
                                  │  • LLM infiere semántica         │
                                  │  • escribe en OM via API         │
                                  └──────────────────────────────────┘
```

## Notas técnicas

- **Base de datos**: PostgreSQL compartido entre OpenMetadata (`openmetadata_db`, `airflow_db`), Superset (`superset`) y la demo (`hotel_demo`). El usuario `artoo_demo` es owner de las bases de la demo.
- **Búsqueda**: OpenSearch 3.4 (Docker Hub) en lugar de Elasticsearch, alineado con el compose de desarrollo de OpenMetadata 1.12. Evita timeouts de pull desde `docker.elastic.co`.
- **Superset**: imagen custom (`superset/Dockerfile`) basada en `apache/superset:4.1.2` con `psycopg2-binary` instalado. La conexión a `hotel_demo` se preregistra automáticamente en el bootstrap.
- **Autenticación OM**: el bootstrap hace login con `admin@open-metadata.org` / `admin` (credenciales por defecto de OM) para obtener un JWT válido. No requiere configuración adicional.
- **Volúmenes**: `make down` borra volúmenes Docker nombrados y el directorio `docker-volume/db-data-postgres/` usando un contenedor Alpine para evitar problemas de permisos.

---

© PoC ARTOO — Logicalis España
