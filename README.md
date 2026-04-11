# ARTOO (PoC)

Demo técnico: **catálogo semántico (OpenMetadata) + LLM** para pasar de preguntas en lenguaje natural a SQL **fundamentado en el esquema**, con una base PostgreSQL de ejemplo (hotel). Detalle funcional y de arquitectura: [`ARTOO_PoC_Specification.md`](ARTOO_PoC_Specification.md).

## Requisitos

- **Docker Desktop** (≥ 20.10) con al menos **6 GiB de RAM** asignados
- **Docker Compose** v2
- **Python 3.12+** y [**uv**](https://docs.astral.sh/uv/) (solo para desarrollo local fuera de Docker)
- Credenciales AWS para Bedrock en `.env.local` (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`), u OpenAI/Anthropic según `LLM_PROVIDER`

## Puesta en marcha

### 1. Configura las variables de entorno

```bash
cp .env.example .env.local
```

Edita `.env.local` y rellena al menos:

| Variable | Descripción |
|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Para Bedrock (IAM key) |
| `LLM_AWS_REGION` | Región de Bedrock (ej. `eu-south-2`) |
| `LLM_API_KEY` | Para OpenAI o Anthropic (alternativa a Bedrock) |
| `ARTOO_DB_PASSWORD` | Contraseña del usuario `artoo_demo` en PostgreSQL |

> `LLM_AWS_PROFILE` debe quedar vacío cuando se usan `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` — los perfiles SSO no están disponibles dentro de los contenedores Docker.

### 2. Arranca el stack completo

```bash
make demo
```

Este comando ejecuta en orden:

1. **`up`** — construye las imágenes propias y levanta todos los servicios
2. **`seed`** — carga ~500 clientes, 6 propiedades, 5.000 reservas y métricas de revenue en `hotel_demo`
3. **`bootstrap`** — espera a que OpenMetadata esté sano, registra el servicio PostgreSQL
4. **`crawl`** — ejecuta el crawler de metadatos directamente via CLI (sin depender de Airflow)
5. **`api`** — levanta la API ARTOO en http://localhost:8000

> El servidor OpenMetadata tarda **3-5 minutos** en quedar listo en el primer arranque.

### 3. Enriquece el catálogo (antes o durante la demo)

```bash
make enrich
```

El enricher:
- Muestrea filas reales de cada tabla
- Calcula estadísticas por columna (valores distintos, top values)
- Para columnas de baja cardinalidad (≤ 20 valores), el LLM infiere el significado de cada código usando los valores reales (ej. `CNCL=Cancelled, CONF=Confirmed`)
- Escribe descripciones y nombres de negocio en OpenMetadata

Esto es lo que permite al chat responder correctamente preguntas como "¿cuántas cancelaciones?" usando `bk_status = 'CNCL'` en lugar de inventar `'Cancelled'`.

## URLs

| Servicio | URL | Credenciales |
|---|---|---|
| Chat + API ARTOO | http://localhost:8000 | — |
| OpenMetadata | http://localhost:8585 | `admin` / `admin` |
| Superset | http://localhost:8088 | `admin` / `admin` |
| Airflow | http://localhost:8080 | `admin` / `admin` |

> Superset arranca con la conexión a `hotel_demo` **ya preconfigurada**. Ve a SQL Lab y empieza a explorar sin configuración adicional.

## Makefile

| Objetivo | Descripción |
|---|---|
| `make demo` | Flujo completo: `up` → `seed` → `bootstrap` → `crawl` → `api` |
| `make up` | Construye imágenes propias y levanta todos los servicios |
| `make seed` | Carga datos demo en `hotel_demo` |
| `make bootstrap` | Registra PostgreSQL en OpenMetadata |
| `make crawl` | Ejecuta el crawl de metadatos via CLI (bypasa Airflow) |
| `make enrich` | Enriquecimiento semántico LLM → catálogo |
| `make api` | Levanta `artoo-api` |
| `make test` | Pytest con cobertura |
| `make lint` | Ruff + mypy |
| `make down` | Para servicios y borra todos los volúmenes |

## Guion de demo en vivo (~5-7 min)

### Preparación (sin audiencia)

Ejecuta `make demo` la noche anterior o con tiempo. Deja el enrich **sin ejecutar** para mostrar el efecto en directo.

### Narrativa sugerida

1. **"El antes"** — Abre **Superset** (http://localhost:8088): el esquema es críptico (`bkng`, `bk_status`, `cust_tier`…). Responder una pregunta de negocio exige conocer los códigos internos (`CNCL`, `BRZ`, etc.).

2. **Chat sin contexto semántico** — Abre http://localhost:8000 y pregunta "¿cuántos clientes premium?". El LLM inventará `cust_tier = 'premium'` → 0 resultados.

3. **Catálogo sin enriquecer** — Abre **OpenMetadata** (http://localhost:8585): tablas y columnas descubiertas pero sin descripciones de negocio.

4. **Enriquecimiento en vivo** — En terminal visible:
   ```bash
   make enrich
   ```
   El enricher muestrea datos reales, llama al LLM y escribe al catálogo en tiempo real.

5. **Catálogo después** — Refresca OpenMetadata: `bk_status` ahora dice `CONF=Confirmed, CNCL=Cancelled, COMP=Completed, NOSH=No-Show`.

6. **"El después" (chat)** — Mismas preguntas, resultados correctos:
   - *¿Cuántos clientes premium tenemos?* → usa `cust_tier = 'PLT'`
   - *¿Qué propiedad tiene más cancelaciones?* → usa `bk_status = 'CNCL'`
   - *Top 10 clientes por gasto total*
   - *NPS medio por propiedad y categoría de habitación*

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
                                  │  • descripciones + códigos       │
                                  │  • clasificaciones PII           │
                                  └──────────▲───────────────────────┘
                                             │ enriquece
                                  ┌──────────┴───────────────────────┐
                                  │       artoo-enricher             │
                                  │  • muestrea filas reales         │
                                  │  • stats por columna             │
                                  │  • LLM infiere semántica         │
                                  │  • documenta códigos exactos     │
                                  └──────────────────────────────────┘
```

## Notas técnicas

- **Credenciales AWS en Docker**: los perfiles SSO (`~/.aws`) no están disponibles dentro de los contenedores. Usar `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` directamente en `.env.local`.
- **Airflow vs CLI**: el contenedor de ingestion usa Airflow 3.x que es incompatible con el plugin de OpenMetadata 1.12. El `make crawl` ejecuta `metadata ingest` directamente via CLI, bypasando Airflow por completo.
- **Columnas codificadas**: el enricher detecta columnas con ≤ 20 valores distintos y el LLM documenta cada código con su significado de negocio. Esto es crítico para que el query pipeline genere SQL correcto.
- **OpenMetadata login**: usar `admin` / `admin` (credenciales por defecto). Si se bloquea la cuenta por intentos fallidos, esperar ~5 minutos.
- **Superset**: imagen custom (`superset/Dockerfile`) basada en `apache/superset:4.1.2` con `psycopg2-binary`. La conexión a `hotel_demo` se preregistra automáticamente en el arranque.
- **Volúmenes**: `make down` borra volúmenes Docker y `docker-volume/db-data-postgres/`. Si falla por permisos: `sudo rm -rf docker-volume/db-data-postgres`.

---

© PoC ARTOO — Logicalis España
