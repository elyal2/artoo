# ARTOO v2 — Especificación Técnica: Capa de Inteligencia Multi-Fuente

> Estado: Borrador · v0.1 · Para revisión con equipo de desarrollo

---

## 1. Visión y objetivo

ARTOO v1 resuelve el problema de hacer preguntas en lenguaje natural sobre datos en PostgreSQL, usando OpenMetadata como catálogo semántico y un LLM para generar SQL.

**ARTOO v2 generaliza ese patrón a cualquier fuente de datos.**

La premisa de negocio es directa: cada proyecto de ingeniería de datos existente en el portfolio de clientes es un candidato. ARTOO se añade como capa de inteligencia encima de la infraestructura que el cliente ya tiene, sin reemplazarla.

```
Proyecto existente del cliente
  + ARTOO
  = AI Ready Data Intelligence Platform
```

**Ejemplos concretos de aplicación:**


| Cliente        | Proyecto           | Fuentes                          | Pregunta ejemplo                                           |
| -------------- | ------------------ | -------------------------------- | ---------------------------------------------------------- |
| MasOrange      | LOGORA             | ELK · BigQuery · logstash        | *"What caused the outage in CCIP yesterday?"*              |
| Barceló Hotels | Kora Golden Record | Confluent · Snowflake            | *"Show me guests with 3+ stays"*                           |
| Moeve          | IoT Platform       | Grafana Cloud · Druid            | *"Which turbines exceeded vibration threshold this week?"* |
| Piñero Group   | Confluent ETL      | Event streams · operational data | *"Summarize booking anomalies in the last 48 hours"*       |


---

## 2. Principios de diseño

1. **El enricher es el componente fundacional.** Sin él, el sistema no sabe qué fuentes existen ni qué preguntas pueden responder. El enricher construye el catálogo que hace posible todo lo demás.
2. **OpenMetadata es el catálogo único y el mecanismo de routing.** Todo asset —independientemente de su origen físico— se registra, enriquece y tagea en OpenMetadata. Los tags y `commonQueries` escritos por el enricher son los que permiten la selección de fuente en tiempo de query.
3. **El routing de fuente es semántico, no configurado.** El sistema no tiene una tabla hardcoded de "esta pregunta va a Snowflake". La selección ocurre vía búsqueda semántica sobre los assets catalogados: los assets que mejor encajan con la pregunta determinan qué adaptadores se activan.
4. **Multi-fuente desde el inicio.** Una pregunta puede requerir datos de más de una fuente. El Query Planner ejecuta queries en paralelo sobre los adaptadores seleccionados y fusiona los resultados antes de pasarlos al LLM.
5. **El chat no conoce el origen físico.** Solo consume catálogo semántico y capacidades declaradas.
6. **El adaptador aisla la complejidad de cada fuente.** Cada fuente tiene un adaptador que implementa una interfaz común.
7. **El LLM genera el lenguaje de consulta correcto por fuente.** SQL para bases relacionales, ES DSL para Elasticsearch, PromQL para Prometheus/Grafana, etc.
8. **Los resultados siempre se normalizan** a `List[Dict[str, Any]]` antes de llegar al chat.
9. **Fail-open en validación.** Si el adaptador no puede validar la query antes de ejecutarla, ejecuta y gestiona el error — no bloquea la respuesta.

---

## 3. Arquitectura general

El sistema tiene dos planos claramente separados:

### Plano offline — El Enricher construye el catálogo

```
  ┌─────────────────────────────────────────────────────────┐
  │                    ARTOO ENRICHER                        │
  │                                                         │
  │  Elasticsearch  Snowflake  Prometheus  Kafka  Druid     │
  │       │             │           │        │       │      │
  │  Source Connector per type (discovery + schema)         │
  │       └─────────────┴───────────┴────────┴───────┘      │
  │                           │                             │
  │                    LLM Enrichment                       │
  │          (descripciones, commonQueries, tags,           │
  │           business_domain, capabilities,                │
  │           adapter_type, query_language)                 │
  │                           │                             │
  └───────────────────────────┼─────────────────────────────┘
                              │ escribe
                    ┌─────────▼─────────┐
                    │   OpenMetadata    │
                    │   (catálogo único)│
                    │                  │
                    │  asset A          │
                    │  · adapter: es    │
                    │  · domain: ops    │
                    │  · commonQueries: │
                    │    ["outages",    │
                    │     "errores"]    │
                    │                  │
                    │  asset B          │
                    │  · adapter: sf    │
                    │  · domain: crm    │
                    │  · commonQueries: │
                    │    ["guests",     │
                    │     "stays"]      │
                    └─────────┬─────────┘
                              │
                    (catálogo disponible para el plano online)
```

### Plano online — Query por pregunta

```
                    Pregunta en lenguaje natural
                               │
                    ┌──────────▼──────────┐
                    │   Intent Classifier  │
                    │   conversational /   │
                    │   data_query         │
                    └──────────┬──────────┘
                               │ data_query
                               │
                    ┌──────────▼──────────────────────────┐
                    │         Source Selector              │
                    │                                      │
                    │  semantic_search(question) → OM      │
                    │  → assets rankeados por relevancia   │
                    │    con adapter_type ya resuelto      │
                    │    (escrito por el enricher)         │
                    └──────────┬──────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    Query Planner     │
                    │                     │
                    │  agrupa assets por  │
                    │  adapter_type →     │
                    │  genera query por   │
                    │  grupo con prompt   │
                    │  específico         │
                    └─────────┬───────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │ (paralelo)        │                   │
  ┌───────▼──────┐   ┌────────▼──────┐   ┌────────▼──────┐
  │ SQL Adapter  │   │Search Adapter │   │Metrics Adapter│
  │ PostgreSQL   │   │Elasticsearch  │   │Prometheus     │
  │ Snowflake    │   │BigQuery (logs)│   │Grafana        │
  │ DuckDB       │   └───────────────┘   │Druid          │
  │ DocumentDB   │                       └───────────────┘
  └──────────────┘
          │                   │                   │
          └───────────────────┴───────────────────┘
                              │ resultados normalizados
                    ┌─────────▼─────────┐
                    │  Result Merger     │
                    │  fusiona datasets  │
                    │  de distintas      │
                    │  fuentes si aplica │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Explanation +    │
                    │  Chart (sin       │
                    │  cambios v1)      │
                    └───────────────────┘
```

---

## 4. Modelo de adaptadores

### 4.1 Interfaz común

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    source_name: str
    query_used: str
    execution_time_ms: int
    row_count: int

@dataclass
class SourceCapabilities:
    query_language: str          # "sql", "es_dsl", "promql", "druid_sql"
    supports_joins: bool
    supports_aggregation: bool
    supports_full_text_search: bool
    is_time_series: bool
    time_field: str | None       # campo temporal principal, si existe
    supports_dry_run: bool       # EXPLAIN o equivalente disponible
    max_result_rows: int

class SourceAdapter(Protocol):
    async def execute(self, query: str) -> QueryResult: ...
    async def dry_run(self, query: str) -> str: ...  # EXPLAIN o validación previa
    def capabilities(self) -> SourceCapabilities: ...
    def query_language_hint(self) -> str: ...        # contexto para el LLM prompt
```

### 4.2 Adaptadores a implementar — prioridad por proyecto


| Prioridad | Adaptador                | Proyectos                     | Query language                              | Complejidad                                           |
| --------- | ------------------------ | ----------------------------- | ------------------------------------------- | ----------------------------------------------------- |
| P1        | **Snowflake**            | Barceló Hotels                | SQL (dialecto Snowflake)                    | Baja — SQL estándar con variantes                     |
| P1        | **Elasticsearch**        | MasOrange                     | ES DSL (JSON)                               | Media — requiere prompt específico                    |
| P2        | **BigQuery**             | MasOrange                     | SQL (dialecto BigQuery)                     | Baja — SQL estándar                                   |
| P2        | **Grafana / Prometheus** | Moeve                         | PromQL                                      | Alta — lenguaje propio para métricas                  |
| P3        | **Druid**                | Moeve                         | Druid SQL                                   | Media — SQL con extensiones temporales                |
| P3        | **Confluent / Kafka**    | Piñero · Barceló              | — (solo lectura de topics via Consumer API) | Alta — no es query language, requiere materialización |
| P4        | **MongoDB / DocumentDB** | Teladoc                       | MQL / Aggregation Pipeline                  | Media                                                 |
| P4        | **DuckDB**               | File-based (S3, Parquet, CSV) | SQL (dialecto DuckDB)                       | Baja                                                  |


### 4.3 Detalle por adaptador

#### Snowflake Adapter

- Conexión vía `snowflake-connector-python`
- SQL generation: mismo `QUERY_SYSTEM_PROMPT` con hint de dialecto Snowflake
- Dry-run: `EXPLAIN` disponible
- Particularidades: `QUALIFY`, funciones de ventana, `FLATTEN` para JSON semiestructurado

#### Elasticsearch Adapter

- Conexión vía `elasticsearch-py`
- Query generation: nuevo prompt `ES_QUERY_SYSTEM_PROMPT` que genera ES DSL en JSON
- Dry-run: `/_validate/query` endpoint
- El LLM genera un JSON de ES DSL, no SQL
- Normalización: `hits.hits._source` → `List[Dict]`
- OpenMetadata registra los índices como assets con sus mappings

#### BigQuery Adapter

- Conexión vía `google-cloud-bigquery`
- SQL generation: mismo prompt con hint BigQuery (`STRUCT`, `UNNEST`, backtick quoting)
- Dry-run: `job.dry_run = True` en la query job → devuelve bytes estimados sin ejecutar

#### Grafana / Prometheus Adapter

- Conexión vía Grafana HTTP API o Prometheus HTTP API
- Query generation: nuevo prompt `PROMQL_SYSTEM_PROMPT`
- El LLM genera PromQL, no SQL
- Dry-run: query con `start=now-1s&end=now` para validar sintaxis sin resultado significativo
- Normalización: matrix/vector response → `List[Dict]` con columnas `timestamp`, `metric_name`, `value`, `labels`
- OpenMetadata registra métricas como assets con su descripción y labels

#### Druid Adapter

- Conexión vía Druid SQL REST API (`/druid/v2/sql`)
- SQL generation: prompt con extensiones temporales de Druid (`TIME_FLOOR`, `TIME_PARSE`)
- Dry-run: `EXPLAIN PLAN FOR ...`

#### Confluent / Kafka Adapter

- **No es queryable directamente.** Dos estrategias posibles:
  - **a) Materialización previa**: el enricher consume el topic, materializa una muestra en DuckDB/S3 y registra el asset con source_type `duckdb`. El chat consulta la materialización.
  - **b) Schema Registry + ksqlDB**: si el cliente tiene ksqlDB desplegado, ARTOO genera ksqlDB SQL y consulta vía REST.
- Recomendación: estrategia (a) para el PoC, (b) para producción.

---

## 5. Extensión del modelo de metadatos en OpenMetadata

Cada asset registrado en OpenMetadata necesita los siguientes custom properties adicionales:

```yaml
# Custom properties en el entity type "table" y nuevo "datasource"

adapter_type:
  type: string
  enum: [postgresql, snowflake, bigquery, elasticsearch, grafana, druid, confluent, duckdb, mongodb]

query_language:
  type: string
  enum: [sql_postgres, sql_snowflake, sql_bigquery, sql_druid, es_dsl, promql, mql, duckdb_sql]

is_time_series:
  type: boolean

time_field:
  type: string   # nombre del campo temporal principal (ej: "@timestamp", "event_time")

supports_dry_run:
  type: boolean

connection_secret_arn:
  type: string   # referencia a AWS Secrets Manager o equivalente

# Ya existentes (mantener):
# commonQueries, PIIType, DataSensitivity, Tier, BusinessTerms
```

---

## 6. El Enricher como componente fundacional

El enricher no es una extensión del sistema — es el componente que hace posible el routing multi-fuente. Sin él, OpenMetadata no contiene los metadatos necesarios para que el Source Selector sepa qué fuentes existen ni qué preguntas pueden responder.

**Flujo de responsabilidad del enricher:**

```
Por cada fuente configurada:

  1. DISCOVERY        → descubre assets (índices, tablas, métricas, topics)
  2. SCHEMA INFERENCE → infiere campos, tipos, cardinalidad
  3. LLM ENRICHMENT  → genera descripciones, commonQueries, tags de negocio
  4. CAPABILITY TAGGING → escribe adapter_type, query_language, is_time_series,
                          time_field, supports_aggregation...
  5. WRITE TO OM      → publica todo en OpenMetadata como assets consultables

El Source Selector en tiempo de query usa exactamente lo que el enricher escribió.
```

### 6.1 Source Discovery por tipo de fuente


| Fuente            | Assets descubiertos                | API de discovery                                                 |
| ----------------- | ---------------------------------- | ---------------------------------------------------------------- |
| **PostgreSQL**    | Tablas, columnas, FKs              | `information_schema` (ya implementado)                           |
| **Elasticsearch** | Índices, field mappings            | `GET /_cat/indices` + `GET /{index}/_mapping`                    |
| **Snowflake**     | Schemas, tablas, columnas, vistas  | `INFORMATION_SCHEMA.COLUMNS`                                     |
| **BigQuery**      | Datasets, tablas, columnas         | `client.list_datasets()` + `table.schema`                        |
| **Prometheus**    | Métricas y sus labels              | `GET /api/v1/label/__name__/values` + `GET /api/v1/metadata`     |
| **Grafana**       | Datasources, paneles, métricas     | Grafana HTTP API                                                 |
| **Druid**         | Datasources, dimensiones, métricas | `GET /druid/v2/datasources` + `GET /druid/v2/datasources/{name}` |
| **Confluent**     | Topics, schemas (Schema Registry)  | Schema Registry REST API                                         |
| **MongoDB/DocDB** | Colecciones, fields (sampling)     | `db.collection.findOne()` × N                                    |


### 6.2 Metadata que el enricher escribe en OpenMetadata

Para cada asset, el enricher escribe:

```
Metadata semántica (LLM-generated):
  · description          → qué representa este asset en términos de negocio
  · commonQueries        → lista de preguntas en NL que este asset puede responder
                           ← CRÍTICO: es el vector de matching del Source Selector
  · business_domain      → dominio de negocio inferido
  · column descriptions  → significado de cada campo/dimensión/label
  · PII tags             → columnas con datos sensibles
  · DataSensitivity tags → nivel de sensibilidad

Metadata técnica (determinística):
  · adapter_type         → "elasticsearch" | "snowflake" | "prometheus" | ...
  · query_language       → "es_dsl" | "sql_snowflake" | "promql" | ...
  · is_time_series       → bool
  · time_field           → nombre del campo temporal principal
  · supports_aggregation → bool
  · supports_dry_run     → bool
  · connection_secret_id → referencia a Secrets Manager
```

### 6.3 El commonQueries como mecanismo de routing

El campo `commonQueries` es el puente entre el lenguaje natural del usuario y el asset correcto:

```
Enricher escribe en el asset "nginx-access-logs" (Elasticsearch):
  commonQueries: [
    "What HTTP errors occurred in the last hour?",
    "Which endpoints have the highest error rate?",
    "What caused the spike in 5xx errors yesterday?",
    "Show me requests by status code"
  ]

Enricher escribe en el asset "bookings" (Snowflake):
  commonQueries: [
    "Show me guests with 3 or more stays",
    "What is the average booking value by channel?",
    "Which hotels have the highest cancellation rate?"
  ]

Pregunta: "What caused the outage in CCIP yesterday?"
  → semantic_search en OM → "nginx-access-logs" score alto
  → adapter_type: elasticsearch → ES DSL prompt
  → NO va a Snowflake bookings (score bajo)
```

### 6.4 Entrypoint CLI extendido

```bash
# Bootstrap + enrich de una fuente concreta
uv run python -m artoo.enricher --source elasticsearch --host http://elk:9200

# Todas las fuentes configuradas en settings
uv run python -m artoo.enricher

# Solo bootstrap (registrar conectores, sin LLM enrichment)
uv run python -m artoo.enricher --bootstrap-only

# Refresh de un asset concreto
uv run python -m artoo.enricher --asset "elasticsearch.nginx-access-logs"
```

---

## 7. Generación de queries por tipo de fuente

### 7.1 Prompts adicionales necesarios


| Prompt                            | Para                 | Genera                             |
| --------------------------------- | -------------------- | ---------------------------------- |
| `QUERY_SYSTEM_PROMPT` (existente) | PostgreSQL, DuckDB   | SQL                                |
| `SNOWFLAKE_QUERY_PROMPT`          | Snowflake            | SQL con dialectos Snowflake        |
| `BIGQUERY_QUERY_PROMPT`           | BigQuery             | SQL con dialectos BigQuery         |
| `ES_QUERY_SYSTEM_PROMPT`          | Elasticsearch        | ES DSL (JSON)                      |
| `PROMQL_SYSTEM_PROMPT`            | Prometheus · Grafana | PromQL                             |
| `DRUID_QUERY_SYSTEM_PROMPT`       | Druid                | Druid SQL con funciones temporales |


### 7.2 Estructura del ES_QUERY_SYSTEM_PROMPT

El LLM debe generar un objeto JSON válido de ES DSL. El `SQLResponse` model necesita un equivalente genérico:

```python
class SourceQueryResponse(BaseModel):
    query: str | dict      # SQL string o ES DSL dict
    query_language: str    # "sql", "es_dsl", "promql", etc.
    assets_used: list[str]
    confidence: Literal["high", "medium", "low"]
    reasoning: str | None
```

### 7.3 Selección de prompt en el Query Planner

```python
PROMPT_BY_LANGUAGE = {
    "sql_postgres":   QUERY_SYSTEM_PROMPT,
    "sql_snowflake":  SNOWFLAKE_QUERY_PROMPT,
    "sql_bigquery":   BIGQUERY_QUERY_PROMPT,
    "es_dsl":         ES_QUERY_SYSTEM_PROMPT,
    "promql":         PROMQL_SYSTEM_PROMPT,
    "sql_druid":      DRUID_QUERY_SYSTEM_PROMPT,
    "duckdb_sql":     QUERY_SYSTEM_PROMPT,  # compatible con postgres prompt
}
```

---

## 8. Retry con feedback de error (existente, extensible)

El mecanismo de retry implementado en v1 (`_generate_sql_with_retry`) se extiende al Query Planner genérico. El error devuelto por cada adaptador (ES parse error, PromQL syntax error, Snowflake compile error) se pasa al LLM como feedback para un segundo intento.

```python
async def _generate_query_with_retry(
    self,
    base_user_msg: str,
    asset: AssetContext,
    max_retries: int = 1,
) -> tuple[SourceQueryResponse, str]:
    # igual que _generate_sql_with_retry pero con adaptador dinámico
    ...
```

---

## 9. Cache de metadatos

Para evitar round-trips a OpenMetadata en cada query:

```python
@dataclass
class AssetCache:
    schema: list[ColumnMeta]
    capabilities: SourceCapabilities
    relationships: list[str]
    sample_stats: dict[str, Any]
    ttl_seconds: int = 900          # 15 min por defecto
    cached_at: datetime = field(default_factory=datetime.utcnow)

    def is_stale(self) -> bool:
        return (datetime.utcnow() - self.cached_at).seconds > self.ttl_seconds
```

- **Desarrollo/demo**: dict en memoria por proceso
- **Producción**: Redis con TTL configurable por asset
- **Invalidación**: el enricher escribe un campo `version` en OM; la cache se invalida si `version` ha cambiado

---

## 10. Configuración

Nuevas variables de entorno necesarias (a añadir a `Settings` en `config.py`):

```env
# Snowflake
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=
SNOWFLAKE_WAREHOUSE=

# Elasticsearch
ELASTICSEARCH_HOST=
ELASTICSEARCH_API_KEY=

# BigQuery
GOOGLE_APPLICATION_CREDENTIALS=   # path al service account JSON
BIGQUERY_PROJECT=

# Grafana
GRAFANA_HOST=
GRAFANA_API_KEY=

# Prometheus (alternativa a Grafana)
PROMETHEUS_HOST=

# Druid
DRUID_HOST=

# Cache
METADATA_CACHE_BACKEND=memory      # "memory" | "redis"
REDIS_URL=redis://localhost:6379/0
METADATA_CACHE_TTL_SECONDS=900
```

---

## 11. Fases de implementación

### Fase 2.0 — Infraestructura base multi-fuente

*Sin esta fase, nada de lo siguiente funciona. Es el prerequisito de todo.*

- `SourceAdapter` protocol + `QueryResult` + `SourceCapabilities` (base.py)
- `PostgreSQLAdapter` — migración del código actual a la interfaz común
- `QueryOrchestrator` — refactor de `QueryPipeline` con selección dinámica de adaptador
- `Source Selector` — semantic search en OM retorna assets con `adapter_type`
- `Result Merger` — fusiona `List[Dict]` de múltiples adaptadores
- `SourceQueryResponse` model genérico (reemplaza `SQLResponse` donde aplique)
- Extensión de OpenMetadata custom properties (`adapter_type`, `query_language`, `is_time_series`, `time_field`, `supports_dry_run`)
- Enricher: refactor para soportar múltiples source connectors con interfaz común
- Cache de metadatos in-memory (TTL configurable)
- Tests: `QueryOrchestrator` con dos adaptadores mock en paralelo

### Fase 2.1 — SQL Adapters + Enrichers

*Objetivo: Barceló Hotels (Snowflake) + MasOrange BigQuery*

- `SnowflakeAdapter` + enricher Snowflake discovery
- `BigQueryAdapter` + enricher BigQuery discovery
- `DuckDBAdapter` (file-based: S3, Parquet, CSV) + enricher file scanner
- `SNOWFLAKE_QUERY_PROMPT` + `BIGQUERY_QUERY_PROMPT`
- Enricher LLM enrichment para assets Snowflake/BigQuery: descripciones, `commonQueries`, tags
- Tests de integración con Snowflake sandbox y BigQuery sandbox

### Fase 2.2 — Search & Logs Adapter + Enricher

*Objetivo: MasOrange ELK (LOGORA)*

- `ElasticsearchAdapter`
- `ES_QUERY_SYSTEM_PROMPT` — el LLM genera ES DSL JSON, no SQL
- Enricher: Elasticsearch index discovery + field mapping enrichment
- Enricher LLM: `commonQueries` orientadas a búsqueda de logs y eventos
- Normalización `hits.hits._source` → `List[Dict]`
- Dry-run vía `/_validate/query`
- Tests de integración con Elasticsearch en Docker

### Fase 2.3 — Metrics Adapter + Enricher

*Objetivo: Moeve (Grafana Cloud + Druid)*

- `PrometheusAdapter` + `GrafanaAdapter`
- `PROMQL_SYSTEM_PROMPT` — el LLM genera PromQL
- Enricher: Prometheus metric discovery (nombres, labels, tipo de métrica)
- Enricher LLM: `commonQueries` orientadas a métricas y umbrales temporales
- Normalización matrix/vector response → `List[Dict]` (`timestamp`, `value`, `labels`)
- `DruidAdapter` + `DRUID_QUERY_SYSTEM_PROMPT`
- Enricher: Druid datasource discovery
- Tests de integración

### Fase 2.4 — Streams Adapter + Enricher

*Objetivo: Piñero Group + Barceló (Confluent)*

- `ConfluentAdapter` — materialización de topics en DuckDB para consulta
- Enricher: Schema Registry connector (descubre schemas Avro/Protobuf/JSON)
- Enricher LLM: `commonQueries` orientadas a eventos y anomalías
- Cache de materialización con TTL configurable por topic
- Tests de integración con Confluent local (Testcontainers)

### Fase 2.5 — Cache Redis + Multi-tenancy

*Prerequisito para producción con múltiples clientes*

- Redis backend para `AssetCache` (namespace por tenant/proyecto)
- Invalidación por evento (enricher publica versión → cache compara al leer)
- Rate limiting por tenant en la API
- `connection_secret_id` por asset — cada adaptador resuelve sus credenciales en runtime

---

## 12. API changes

El endpoint `POST /api/query` no cambia de contrato externamente. Internamente:

```python
class QueryRequest(BaseModel):
    question: str
    history: list[ConversationMessage] | None = None
    source_filter: list[str] | None = None  # NUEVO: filtrar por assets concretos
```

Nuevo endpoint de administración:

```
POST /api/admin/refresh-cache/{asset_fqn}   # invalida cache de un asset
GET  /api/admin/sources                     # lista fuentes registradas con estado
GET  /api/admin/sources/{fqn}/schema        # schema cacheado de un asset
```

---

## 13. Estructura de directorios propuesta

```
src/artoo/
├── api/
│   ├── server.py
│   ├── pipeline.py          → renombrar a orchestrator.py
│   └── validator.py
├── adapters/                ← NUEVO
│   ├── __init__.py
│   ├── base.py              (SourceAdapter protocol, QueryResult, SourceCapabilities)
│   ├── postgresql.py
│   ├── snowflake.py
│   ├── bigquery.py
│   ├── elasticsearch.py
│   ├── grafana.py
│   ├── prometheus.py
│   ├── druid.py
│   ├── confluent.py
│   └── duckdb.py
├── catalog/
│   ├── openmetadata.py
│   └── cache.py             ← NUEVO
├── enricher/
│   ├── __main__.py
│   ├── enricher.py
│   ├── collector.py
│   ├── writer.py
│   └── sources/             ← NUEVO
│       ├── elasticsearch.py
│       ├── snowflake.py
│       ├── bigquery.py
│       ├── prometheus.py
│       └── druid.py
├── llm/
│   ├── client.py
│   └── prompts.py           (añadir prompts por fuente)
├── config.py
└── models.py
```

---

## 14. Riesgos y decisiones pendientes


| Riesgo                                                 | Probabilidad | Mitigación                                                                          |
| ------------------------------------------------------ | ------------ | ----------------------------------------------------------------------------------- |
| El LLM genera ES DSL inválido frecuentemente           | Media        | Retry con error; fallback a query simple (`match_all` filtrado)                     |
| PromQL syntax es complejo para el LLM                  | Alta         | Ejemplos en el prompt; validación con Prometheus antes de ejecutar                  |
| Latencia alta en Snowflake para queries de exploración | Media        | Cache de resultados frecuentes; LIMIT agresivo por defecto                          |
| Kafka no es queryable directamente                     | Certeza      | Estrategia de materialización en DuckDB definida en sección 4.3                     |
| Multi-tenancy: credentials por cliente                 | Alta         | Un `connection_secret_arn` por asset en OpenMetadata; adaptador resuelve en runtime |


**Decisiones pendientes que el equipo debe tomar antes de Fase 2.1:**

1. ¿La cache es in-memory siempre o Redis desde el primer sprint?
2. ¿El `QueryOrchestrator` maneja queries multi-fuente (cruce de datos entre Snowflake y Elasticsearch) o solo mono-fuente en v2?
3. ¿El enricher se ejecuta manualmente o hay un scheduler automático para discovery?
4. ¿Cómo se gestiona la rotación de credenciales de cada adaptador (Secrets Manager, Vault, variables de entorno)?

---

## 15. Criterios de aceptación por fase

### Fase 2.1 completa cuando:

- Una pregunta sobre datos de Snowflake genera SQL Snowflake correcto, lo ejecuta, y devuelve resultado con chart
- Una pregunta sobre datos de BigQuery ídem con dialecto BigQuery
- Los tests unitarios de `SnowflakeAdapter` y `BigQueryAdapter` pasan con mocks

### Fase 2.2 completa cuando:

- Una pregunta como "what caused the outage in CCIP yesterday?" genera ES DSL válido, lo ejecuta sobre un índice Elasticsearch de test, y devuelve resultado
- El enricher descubre y documenta los mappings de un índice Elasticsearch en OpenMetadata

### Fase 2.3 completa cuando:

- Una pregunta como "which turbines exceeded vibration threshold this week?" genera PromQL válido, lo ejecuta sobre Prometheus de test, y devuelve una serie temporal normalizada con chart de línea

### Fase 2.4 completa cuando:

- Un topic de Kafka se materializa automáticamente en DuckDB al registrarse en OpenMetadata
- Las preguntas sobre ese topic se resuelven consultando la materialización

---

*v0.1 — Para revisión con equipo de desarrollo. Sujeto a cambios tras decisiones de arquitectura pendientes (sección 14).*