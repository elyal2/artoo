# ARTOO

> **Consulta tus datos en lenguaje natural. Con contexto de negocio real.**

ARTOO es un asistente de datos semántico que conecta un catálogo de metadatos con un LLM para responder preguntas sobre tus datos sin que nadie tenga que escribir SQL.

No es un chatbot genérico conectado a una base de datos. La diferencia está en el catálogo: ARTOO enriquece el esquema con descripciones de negocio, clasificaciones PII, valores codificados y relaciones entre tablas, y usa ese conocimiento para generar consultas precisas, validarlas antes de ejecutarlas, y devolver los resultados con la visualización más adecuada.

## El problema que resuelve

Los datos están en bases de datos. El contexto de negocio está en las cabezas de las personas o, con suerte, en un catálogo de datos. Unir ambas cosas para que cualquier persona pueda explorar los datos sin fricción técnica es difícil.

Las soluciones habituales fallan porque:
- Los chatbots SQL genéricos no conocen el significado de las columnas ni sus valores codificados, y cometen errores semánticos.
- Los catálogos de datos documentan bien el esquema, pero no tienen interfaz conversacional.
- Las herramientas de BI requieren conocimiento técnico para configurar y usar.

## Cómo funciona ARTOO

```
Pregunta en lenguaje natural
        │
        ▼
Clasificación de intención
  ├── conversacional → respuesta directa
  └── consulta de datos
              │
              ▼
        OpenMetadata
   (schema + semántica + FK)
              │
              ▼
     LLM genera SQL
   (usando columnas y valores reales)
              │
              ▼
   Validación + EXPLAIN dry-run
              │
              ▼
    Postgres ejecuta la query
              │
              ▼
   LLM elige y genera visualización
   (D3.js: bar, line, bubble, heatmap…)
              │
              ▼
      Resultado en el chat
```

1. **Crawl** — OpenMetadata descubre el esquema de la base de datos.
2. **Enriquecimiento** — el enricher de ARTOO muestrea filas reales, infiere significado de negocio para cada columna y cada valor, y escribe ese conocimiento en el catálogo.
3. **Consulta** — el usuario pregunta en lenguaje natural. ARTOO recupera el contexto semántico del catálogo, genera SQL usando los nombres y valores exactos del esquema, lo valida antes de ejecutarlo, y presenta los resultados con una gráfica o una tabla.

## Por qué importa el catálogo semántico

Sin enriquecimiento, un LLM conectado a una base de datos no sabe que `bk_status = 'COMP'` significa "completada", o que `pay_meth` tiene seis valores posibles y cuáles son. Inventará columnas, usará valores incorrectos y producirá SQL que falla o que devuelve resultados equivocados.

Con ARTOO, el catálogo describe el esquema en términos de negocio: qué almacena cada tabla, qué significa cada columna, qué valores toma. Ese contexto es el que llega al LLM, no el esquema técnico en crudo.

## Para quién es

- **Data analysts y product managers** que quieren explorar datos sin depender del equipo técnico.
- **Equipos de datos** que quieren demostrar el valor de su catálogo de metadatos.
- **Proyectos de IA sobre datos** que necesitan una capa semántica antes de conectar un LLM a una base de datos.

## Qué incluye

| Componente | Descripción |
|---|---|
| **artoo-api** | API FastAPI + interfaz de chat. Recibe preguntas, genera SQL, valida, ejecuta y devuelve resultados con visualización D3. |
| **artoo-enricher** | Proceso de enriquecimiento semántico. Muestrea datos, infiere significado, aplica tags PII/sensibilidad/tier y escribe todo en OpenMetadata. |
| **OpenMetadata** | Catálogo de metadatos. Almacena el esquema enriquecido con descripciones, relaciones, glosario y clasificaciones. |
| **Chat UI** | Interfaz conversacional en el navegador. Routing por intención, gráficas automáticas, historial, sidebar de tablas, tema claro/oscuro. |
| **MCP endpoint** | `/mcp` expone las capacidades como herramientas MCP para integrar ARTOO con agentes externos. |

## Demos incluidas

ARTOO incluye perfiles de demo intercambiables para arrancar con datos de ejemplo sin configuración adicional:

| Perfil | Dominio | Tablas |
|---|---|---|
| `hotel` (defecto) | Hostelería | reservas, clientes, propiedades, revenue, experiencia |
| `ecommerce` | E-commerce | clientes, productos, pedidos, líneas, reviews |
| `andorra` | Gobierno | turismo, indicadores_economicos, tributos, presupuesto |

---

## Requisitos

- **Docker Desktop** (≥ 20.10) con al menos **6 GiB de RAM** asignados
- **Docker Compose** v2
- **Python 3.12+** y [**uv**](https://docs.astral.sh/uv/) (solo para desarrollo local fuera de Docker)
- Credenciales LLM: Bedrock (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`), OpenAI, o Anthropic

> Para charts de calidad se recomienda un modelo más capaz en `LLM_CHART_MODEL` (ej. Claude Sonnet). El modelo base (`LLM_MODEL`) puede ser más ligero para SQL y clasificación.

## Puesta en marcha

### 1. Configura las variables de entorno

```bash
cp .env.example .env.local
```

Edita `.env.local` y rellena al menos:

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | `bedrock`, `openai` o `anthropic` |
| `LLM_MODEL` | Modelo base para SQL (ej. `eu.amazon.nova-lite-v1:0` para Bedrock EU) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Para Bedrock (IAM key) |
| `LLM_AWS_REGION` | Región de Bedrock (ej. `eu-south-2`) |
| `LLM_API_KEY` | Para OpenAI o Anthropic (alternativa a Bedrock) |
| `LLM_INTENT_MODEL` | *(Opcional)* Modelo para clasificación de intención (ej. `eu.amazon.nova-lite-v1:0`) |
| `LLM_EXPLANATION_MODEL` | *(Opcional)* Modelo para interpretación de resultados (ej. `eu.amazon.nova-lite-v1:0`) |
| `LLM_CHART_MODEL` | Modelo para generación de gráficas (recomendado: `eu.anthropic.claude-sonnet-4-20250514-v1:0`) |
| `ENRICHMENT_LLM_MODEL` | *(Opcional)* Modelo para enricher (ej. `eu.amazon.nova-lite-v1:0` para ahorro de costes) |
| `ARTOO_DB_PASSWORD` | Contraseña del usuario `artoo_demo` en PostgreSQL |
| `DEMO_PROFILE` | *(Opcional)* Perfil demo: `hotel`, `ecommerce`, `andorra` (defecto: `hotel`) |
| `OPENMETADATA_DB_FILTER` | *(Opcional)* FQN del servicio/base de datos a enriquecer |

> **Importante**: En regiones Bedrock EU (`eu-south-2`), todos los model IDs deben usar prefijo `eu.` (ej. `eu.amazon.nova-lite-v1:0`). Los modelos sin prefijo fallan con `ValidationException: inference profile required`.

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
- Glosario `BusinessTerms` para términos de negocio
- Glosario `UnidadesMedida` para unidades métricas (Millones_EUR, Porcentaje_0_100, Euros, etc.)
- Custom property `commonQueries` en el tipo `table`

**Enriquecimiento semántico por tabla**:
- Muestrea filas reales y calcula estadísticas por columna
- Para columnas de baja cardinalidad (≤ 20 valores), el LLM documenta cada código
- Detecta unidades de medida (millones EUR, porcentajes, etc.) y asigna glossary terms `UnidadesMedida.*`
- Escribe en OpenMetadata: descripciones, tags PII, sensibilidad, tiers, dominios, glosario, unidades

Este paso es el que convierte el catálogo técnico en contexto de negocio. Sin él, la calidad del SQL generado es significativamente peor.

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
- **Respuestas conversacionales** — si la pregunta no requiere datos, responde directamente sin generar SQL
- **Resultados con chart o tabla** — el LLM elige el tipo de gráfico más adecuado (bar, line, bubble, heatmap, donut, etc.) y genera código D3 v7
- **Historial de conversación** — el contexto de preguntas anteriores se mantiene para queries multi-turno
- **Panel de ayuda** — botón `?` en el header con todos los tipos de gráfico disponibles y ejemplos
- **Tema claro/oscuro** — toggle en el header, persistido en localStorage
- **Sidebar con tablas** — lista de tablas disponibles del catálogo; clic para precargar una consulta

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

- **OpenMetadata 1.5.8**: versión actualizada con mejor soporte para glossary terms en API. Migración desde 1.2.4 incluye backup automático.
- **Inference Profiles en Bedrock**: en regiones EU (`eu-south-2`), usar prefijo `eu.` en model IDs: `eu.amazon.nova-lite-v1:0`, `eu.anthropic.claude-sonnet-4-20250514-v1:0`. Sin prefijo falla con `ValidationException`.
- **Cache de configuración Docker**: cambios en `.env.local` requieren `docker compose stop <service> && docker compose rm -f <service> && docker compose up -d <service>` para recargar env vars. `docker compose restart` **NO** recarga la configuración de pydantic-settings.
- **Credenciales AWS en Docker**: los perfiles SSO (`~/.aws`) no están disponibles dentro de los contenedores. Usar `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` directamente en `.env.local`.
- **Airflow vs CLI**: el contenedor de ingestion usa Airflow 3.x incompatible con el plugin de OpenMetadata 1.5.8. `make crawl` ejecuta `metadata ingest` directamente via CLI.
- **Columnas codificadas**: el enricher detecta columnas con ≤ 20 valores distintos y el LLM documenta cada código con su significado de negocio. Crítico para SQL correcto.
- **Unidades de medida**: el enricher detecta patrones en nombres de columnas (`*_millones_eur`, `*_pct`, `*_mill`, etc.) y asigna glossary terms automáticamente. Los post-procesadores mejoran las explicaciones añadiendo contexto de unidades.
- **Governance genérico**: el enricher no asume ningún dominio. Los dominios se infieren del LLM y se crean automáticamente en OpenMetadata. Funciona con cualquier esquema.
- **Charts**: para gráficas de calidad, configurar `LLM_CHART_MODEL` con un modelo más capaz que el de SQL (ej. Claude Sonnet). Si no hay gráfica, revisar los logs por `Chart generation failed`.
- **Intent classification**: para routing conversacional/data_query preciso, configurar `LLM_INTENT_MODEL` con un modelo más capaz (ej. Claude Haiku). Nova Lite puede fallar en preguntas hipotéticas complejas ("¿qué pasaría si...?").
- **OpenMetadata login**: `admin@openmetadata.org` / `admin` (defecto). Si se bloquea la cuenta, esperar ~5 minutos.
- **Superset**: imagen custom basada en `apache/superset:4.1.2` con `psycopg2-binary`. La conexión a la demo se preregistra automáticamente.
- **Volúmenes**: `make down` borra volúmenes Docker y `docker-volume/db-data-postgres/`. Si falla por permisos: `sudo rm -rf docker-volume/db-data-postgres`.
- **Demos mixtos**: `DEMO_PROFILE=andorra` carga datos de gobierno sin truncar las tablas del demo hotel. Ambos datasets coexisten en la misma base de datos para testing cross-domain.

---

© PoC ARTOO — Logicalis España
