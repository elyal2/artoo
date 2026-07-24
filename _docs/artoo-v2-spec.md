# ARTOO v2 — Product Requirements Document

> Versión: v0.2 · Estado: Borrador para revisión
> Cambios v0.2: integración Apache Ossie, capa semántica de consumo, PRD estructurado para SDD

---

## Índice

1. [Visión y Contexto de Negocio](#1-visión-y-contexto-de-negocio)
2. [Problema que Resuelve](#2-problema-que-resuelve)
3. [Objetivos y Métricas de Éxito](#3-objetivos-y-métricas-de-éxito)
4. [Alcance Funcional](#4-alcance-funcional)
5. [Arquitectura General](#5-arquitectura-general)
6. [Módulo A — Enricher](#6-módulo-a--enricher)
7. [Módulo B — Catálogo Semántico](#7-módulo-b--catálogo-semántico)
8. [Módulo C — Capa Semántica de Consumo (Ossie)](#8-módulo-c--capa-semántica-de-consumo-ossie)
9. [Módulo D — Query Orchestrator](#9-módulo-d--query-orchestrator)
10. [Módulo E — Adaptadores de Fuente](#10-módulo-e--adaptadores-de-fuente)
11. [Módulo F — API y Chat](#11-módulo-f--api-y-chat)
12. [Dependencias entre Módulos](#12-dependencias-entre-módulos)
13. [Fases de Implementación](#13-fases-de-implementación)
14. [Riesgos y Mitigaciones](#14-riesgos-y-mitigaciones)
15. [Decisiones Pendientes](#15-decisiones-pendientes)
16. [Apéndices](#16-apéndices)

---

## 1. Visión y Contexto de Negocio

### 1.1 Qué es ARTOO

ARTOO es una capa de inteligencia en lenguaje natural que se añade encima de la infraestructura de datos que el cliente ya tiene, sin reemplazarla. Combina un catálogo semántico enriquecido con IA (OpenMetadata), una capa semántica de consumo estándar (Apache Ossie), y un motor de consulta multi-fuente (adaptadores + LLM).

```
Proyecto existente del cliente
  + ARTOO
  = AI Ready Data Intelligence Platform
```

### 1.2 Premisa de negocio

Cada proyecto de ingeniería de datos en el portfolio de Logicalis es un candidato. El mercado objetivo son clientes que:

- Tienen datos distribuidos en múltiples fuentes (BDs, logs, métricas, eventos)
- Quieren que sus usuarios de negocio consulten datos sin escribir SQL
- Ya tienen (o están evaluando) un catálogo de datos (Informatica CDGC, OpenMetadata)
- Están considerando capas semánticas propietarias (Mosaic/MicroStrategy, dbt Semantic Layer) y quieren alternativas open source

### 1.3 Posicionamiento competitivo

| Alternativa | Territorio | Diferenciación ARTOO |
|---|---|---|
| **Mosaic (MicroStrategy)** | Capa consumo + BI | Sin lock-in, sin licencia por usuario, Ossie estándar |
| **dbt Semantic Layer** | Capa consumo | No requiere reescribir el stack en dbt |
| **Informatica CLAIRE** | Capa gobierno | Enriquecimiento con datos reales, no solo metadatos estructurales |
| **OpenMetadata solo** | Capa gobierno | Añade capa de consumo + LLM query |

### 1.4 Casos de uso objetivo

| Cliente | Proyecto | Fuentes | Pregunta ejemplo |
|---|---|---|---|
| MasOrange | LOGORA | ELK · BigQuery · logstash | *"¿Qué causó el outage en CCIP ayer?"* |
| Barceló Hotels | Kora Golden Record | Confluent · Snowflake | *"Muéstrame huéspedes con 3+ estancias"* |
| Moeve | IoT Platform | Grafana Cloud · Druid | *"¿Qué turbinas superaron el umbral de vibración esta semana?"* |
| Govern Andorra | Open Data | PostgreSQL | *"¿Qué porcentaje del PIB depende del turismo?"* |

---

## 2. Problema que Resuelve

### 2.1 Problema de gobierno (capa semántica de gobierno)

Los catálogos automáticos (CLAIRE, Atlas, Collibra scanner) infieren metadatos a partir de nombres de columna y tipos de dato. No miran dentro de los datos.

**Ejemplo real:** CLAIRE ve `bk_status VARCHAR(5)` y lo describe como *"campo de estado"*. El enricher ve `'COMP'`, `'PEND'`, `'CANC'` en los datos reales y documenta: *"Estado de reserva: COMP=completada, PEND=pendiente de validación, CANC=cancelada. 3% de nulos en registros anteriores a 2019."*

### 2.2 Problema de consumo (capa semántica de consumo)

Las métricas de negocio se definen de forma diferente en cada herramienta (Tableau, Power BI, Excel, agentes IA). No hay una fuente única de verdad para el cálculo de KPIs.

**Ejemplo real:** *"Ingresos por turismo"* se calcula como `SUM(visitantes * gasto_medio)` en Tableau, pero como `SUM(gasto_total)` en Power BI — con resultados distintos.

### 2.3 Problema de acceso (lenguaje natural)

Los usuarios de negocio no pueden consultar datos directamente. Dependen de analistas para cada pregunta nueva. Los LLMs sin contexto de catálogo generan SQL que alucina nombres de columnas, unidades y relaciones.

### 2.4 Problema de fragmentación (multi-fuente)

Las organizaciones tienen datos en BDs, logs, métricas y eventos. Cada fuente tiene su propio lenguaje de consulta. No hay forma de hacer una pregunta que cruce múltiples fuentes sin un desarrollo a medida.

---

## 3. Objetivos y Métricas de Éxito

### 3.1 Objetivos de producto

| # | Objetivo | Métrica de éxito | Target |
|---|---|---|---|
| O1 | Queries en lenguaje natural correctas | % de preguntas que devuelven resultado sin error SQL | ≥85% |
| O2 | Enriquecimiento automático de catálogo | Tiempo de enriquecimiento por asset (50 tablas) | ≤10 min |
| O3 | Cobertura semántica | % de assets con descripción, commonQueries y unidades documentadas | ≥90% |
| O4 | Coste de operación LLM | Coste por query (generación SQL + explicación) | ≤$0.01 |
| O5 | Onboarding de cliente | Tiempo desde despliegue hasta primera query exitosa en datos reales del cliente | ≤1 semana |

### 3.2 Objetivos de negocio

| # | Objetivo | Métrica | Target |
|---|---|---|---|
| B1 | Conversión de PoC a proyecto | % de PoCs que pasan a fase de producción | ≥60% |
| B2 | Reutilización del enricher | Nº de clientes que adoptan el enricher independientemente del query layer | ≥3 en año 1 |
| B3 | Posicionamiento frente a Mosaic | Nº de clientes que eligen ARTOO tras evaluar Mosaic | ≥2 en año 1 |

---

## 4. Alcance Funcional

### 4.1 En scope

| Funcionalidad | Descripción |
|---|---|
| Discovery automático de assets | El enricher descubre tablas, índices, métricas y topics por tipo de fuente |
| Enriquecimiento semántico con LLM | Descripciones, commonQueries, unidades, PII, dominio — generados con datos reales |
| Escritura en OpenMetadata | Tags, glossary terms, custom properties, dominios — idempotente |
| Exportación Ossie YAML | Métricas y datasets en formato estándar Apache Ossie |
| Semantic search para routing | Búsqueda en OM por significado, no por nombre exacto |
| Query en lenguaje natural | SQL, ES DSL, PromQL generado por LLM según adaptador |
| Multi-fuente en paralelo | Ejecutar queries en varias fuentes y fusionar narrativamente |
| Intent classification | Conversacional vs data_query antes de generar SQL |
| Validación de queries | AST parsing + EXPLAIN dry-run antes de ejecutar |
| Visualización automática | D3.js charts recomendados por el LLM |
| Chat UI | Interfaz web con sidebar de catálogo, historial, charts |

### 4.2 Fuera de scope (v2)

| Funcionalidad | Razón |
|---|---|
| JOIN estructural entre fuentes heterogéneas | Requiere motor de federación — complejidad excesiva para v2 |
| Escritura de datos | ARTOO es read-only por diseño |
| Autenticación y autorización por usuario | Depende del IAM del cliente — integración por proyecto |
| Scheduler automático de enriquecimiento | v2 usa ejecución manual/CI-CD |
| Materialización de queries frecuentes | Sin caché de resultados en v2 (solo caché de metadatos) |
| Versionado de modelos semánticos | Ossie 0.2.0 no lo soporta — esperar a estabilización |

### 4.3 Roadmap explícito (v3+)

- Materialización de queries frecuentes con TTL
- Scheduler de enriquecimiento (Airflow / GitHub Actions)
- JOIN federado entre fuentes (DuckDB como motor de federación)
- Versionado de modelos Ossie
- Multi-tenancy con RBAC por tenant

---

## 5. Arquitectura General

### 5.1 Vista de alto nivel

```
┌─────────────────────────────────────────────────────────────────┐
│                        PLANO OFFLINE                             │
│                                                                  │
│  Fuentes de datos                                                │
│  PostgreSQL · Elasticsearch · Snowflake · BigQuery · Prometheus  │
│       │                                                          │
│  ┌────▼────────────────────────────────────────────────────┐    │
│  │              MÓDULO A — ENRICHER                         │    │
│  │  Discovery → Schema Inference → LLM Enrichment → Write   │    │
│  └────┬────────────────────────────────────────────────────┘    │
│       │ escribe                                                  │
│  ┌────▼──────────────┐  ┌─────────────────────────────────────┐ │
│  │  MÓDULO B         │  │  MÓDULO C                           │ │
│  │  OpenMetadata     │  │  Ossie YAML                         │ │
│  │  (gobernanza)     │  │  (capa semántica de consumo)        │ │
│  │                   │  │                                     │ │
│  │  · descripciones  │  │  · métricas gobernadas              │ │
│  │  · PII tags       │  │  · datasets + relationships         │ │
│  │  · linaje         │  │  · ai_context (synonyms, examples)  │ │
│  │  · commonQueries  │  │  · custom_extensions (vendor)       │ │
│  └───────────────────┘  └─────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │ lee
┌─────────────────────────────▼───────────────────────────────────┐
│                        PLANO ONLINE                              │
│                                                                  │
│  Pregunta en lenguaje natural                                    │
│       │                                                          │
│  ┌────▼────────────────────────────────────────────────────┐    │
│  │              MÓDULO D — QUERY ORCHESTRATOR               │    │
│  │  Intent → Source Selector → Query Planner → Adapters     │    │
│  └────┬────────────────────────────────────────────────────┘    │
│       │                                                          │
│  ┌────▼────────────────────────────────────────────────────┐    │
│  │              MÓDULO E — ADAPTADORES DE FUENTE            │    │
│  │  PostgreSQL · Elasticsearch · Snowflake · BigQuery · ... │    │
│  └────┬────────────────────────────────────────────────────┘    │
│       │ resultados normalizados                                  │
│  ┌────▼────────────────────────────────────────────────────┐    │
│  │              MÓDULO F — API + CHAT                       │    │
│  │  Explanation · Chart · History · Sidebar                 │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Principios de diseño

1. **El enricher es el componente fundacional.** Sin él, el sistema no sabe qué fuentes existen ni qué preguntas pueden responder.
2. **OpenMetadata es el catálogo de gobierno; Ossie YAML es la capa de consumo.** Dos formatos, un mismo origen: el enricher escribe en ambos.
3. **El routing de fuente es semántico, no configurado.** La selección de adaptador ocurre vía búsqueda semántica sobre los assets catalogados.
4. **El chat no conoce el origen físico.** Solo consume catálogo semántico y capacidades declaradas.
5. **El adaptador aisla la complejidad de cada fuente.** Cada fuente implementa `SourceAdapter` Protocol.
6. **Los resultados siempre se normalizan** a `List[Dict[str, Any]]` antes de llegar al chat.
7. **Fail-open en validación.** Si el adaptador no puede validar antes de ejecutar, ejecuta y gestiona el error.
8. **Ossie es opcional pero recomendado.** El sistema funciona sin Ossie (solo OM), pero la exportación Ossie habilita la interoperabilidad con dbt, GoodData, Tableau, etc.
9. **No hay lock-in.** Todos los metadatos se escriben en formatos estándar (OpenMetadata API + Ossie YAML) que el cliente puede consumir independientemente de ARTOO.
10. **Un cliente, una fuente, una semana.** El caso de entrada mínimo es una fuente de datos bien enriquecida, no ocho fuentes mal conectadas.

---

## 6. Módulo A — Enricher

### 6.1 Propósito

Construir y mantener el catálogo semántico que hace posible todo lo demás. El enricher no es una extensión — es el prerrequisito.

### 6.2 Responsabilidades

| Responsabilidad | Descripción |
|---|---|
| Discovery | Descubrir assets en cada fuente (tablas, índices, métricas, topics) |
| Schema inference | Inferir campos, tipos, cardinalidad, FKs |
| LLM enrichment | Generar descripciones, commonQueries, dominios, tags |
| Capability tagging | Escribir adapter_type, query_language, is_time_series, time_field |
| OM writer | Escribir en OpenMetadata (idempotente) |
| Ossie writer | Generar Ossie YAML con métricas y datasets |
| Stats collection | Muestrear filas reales para estadísticas de columna |

### 6.3 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| A-RF1 | Discovery de PostgreSQL via `information_schema` | P0 |
| A-RF2 | Discovery de Elasticsearch via `_cat/indices` + `_mapping` | P1 |
| A-RF3 | Discovery de Snowflake via `INFORMATION_SCHEMA.COLUMNS` | P1 |
| A-RF4 | Discovery de BigQuery via `list_datasets()` + `table.schema` | P2 |
| A-RF5 | Discovery de Prometheus via `/api/v1/label/__name__/values` | P2 |
| A-RF6 | Discovery de Druid via `/druid/v2/datasources` | P3 |
| A-RF7 | Discovery de Confluent via Schema Registry REST API | P3 |
| A-RF8 | Stats collection con muestreo de filas reales (asyncpg/directo) | P0 |
| A-RF9 | LLM enrichment con fallback robusto si el JSON está truncado | P0 |
| A-RF10 | commonQueries orientadas a lenguaje de negocio del dominio | P0 |
| A-RF11 | Detección automática de unidades (83 patrones regex) | P0 |
| A-RF12 | Detección automática de PII con coerción de sensibilidad | P0 |
| A-RF13 | Escritura idempotente en OM (replace atómico de tags) | P0 |
| A-RF14 | Generación de Ossie YAML con métricas inferidas | P1 |
| A-RF15 | Escritura de `adapter_type`, `query_language`, `time_field` en OM | P0 |
| A-RF16 | Soporte para `--source <tipo>` y `--asset <fqn>` en CLI | P0 |
| A-RF17 | Concurrencia controlada vía semáforo (`ENRICHMENT_CONCURRENCY`) | P0 |
| A-RF18 | `--bootstrap-only` para registrar conectores sin LLM enrichment | P0 |

### 6.4 commonQueries — orientación a negocio

Las `commonQueries` son el vector de matching del Source Selector. Deben usar el **lenguaje del negocio del cliente**, no el lenguaje técnico del sistema:

```
MAL (técnico):
  "What HTTP errors occurred in the last hour?"
  "Which endpoints have the highest error rate?"

BIEN (negocio):
  "¿Por qué cayó el servicio de facturación ayer?"
  "¿Cuántos usuarios se vieron afectados por el outage de esta mañana?"

MAL (técnico):
  "Show me guests with 3 or more stays"

BIEN (negocio):
  "¿Qué huéspedes han vuelto al hotel más de 3 veces este año?"
  "¿Cuál es la tasa de fidelización de clientes por canal de reserva?"
```

El LLM del enricher recibe el `business_domain` como contexto para generar preguntas en el idioma y registro del dominio (español para clientes españoles, inglés para MasOrange, etc.).

### 6.5 Entrada y salida

**Entrada:** configuración de fuentes (DSN, hosts, credenciales), lista de assets a enriquecer.

**Salida:**
- OpenMetadata actualizado con descripciones, tags, commonQueries, dominios
- Ossie YAML por asset en `_ossie/` (o registrado en OM como custom property)

### 6.6 CLI

```bash
# Enriquecer todas las fuentes configuradas
uv run python -m artoo.enricher

# Solo una fuente concreta
uv run python -m artoo.enricher --source elasticsearch --host http://elk:9200

# Solo bootstrap (registrar conectores, sin LLM enrichment)
uv run python -m artoo.enricher --bootstrap-only

# Refresh de un asset concreto
uv run python -m artoo.enricher --asset "elasticsearch.nginx-access-logs"

# Solo exportar Ossie YAML (sin escribir en OM)
uv run python -m artoo.enricher --ossie-only --output ./_ossie/
```

### 6.7 Dependencias

| Dependencia | Versión | Propósito |
|---|---|---|
| OpenMetadata API | 1.5.8 | Escritura de metadatos |
| AWS Bedrock (Nova Lite) | eu-south-2 | LLM enrichment |
| asyncpg | ≥0.30 | Stats collection PostgreSQL |
| httpx | — | Cliente HTTP async |

---

## 7. Módulo B — Catálogo Semántico

### 7.1 Propósito

OpenMetadata como fuente única de verdad para metadatos de gobierno: qué significa cada dato, de dónde viene, quién puede verlo.

### 7.2 Metadata que almacena

```
Metadata semántica (escrita por el enricher):
  · description          → qué representa este asset en términos de negocio
  · commonQueries        → preguntas en NL que este asset puede responder
  · business_domain      → dominio de negocio inferido
  · column descriptions  → significado de cada campo/dimensión/label
  · PII tags             → columnas con datos sensibles
  · DataSensitivity tags → nivel de sensibilidad

Metadata técnica (escrita por el enricher):
  · adapter_type         → "elasticsearch" | "snowflake" | "prometheus" | ...
  · query_language       → "es_dsl" | "sql_snowflake" | "promql" | ...
  · is_time_series       → bool
  · time_field           → nombre del campo temporal principal
  · supports_aggregation → bool
  · supports_dry_run     → bool
  · connection_secret_id → referencia a Secrets Manager
```

### 7.3 Custom properties requeridas

```yaml
adapter_type:
  type: string
  enum: [postgresql, snowflake, bigquery, elasticsearch, grafana, druid, confluent, duckdb, mongodb]

query_language:
  type: string
  enum: [sql_postgres, sql_snowflake, sql_bigquery, sql_druid, es_dsl, promql, mql, duckdb_sql]

is_time_series:
  type: boolean

time_field:
  type: string

supports_dry_run:
  type: boolean

connection_secret_arn:
  type: string

ossie_model_ref:
  type: string   # referencia al Ossie YAML asociado (si existe)
```

### 7.4 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| B-RF1 | `list_tables()` devuelve `business_domain` (campo `domain` en OM API) | P0 |
| B-RF2 | `semantic_search()` normaliza queries y maneja errores gracefully | P0 |
| B-RF3 | `get_table()` devuelve `tags` por columna (glossary terms) | P0 |
| B-RF4 | Custom properties registradas en bootstrap del enricher | P0 |
| B-RF5 | `generate_conversion_rules()` lee tags `UnidadesMedida.*` | P0 |
| B-RF6 | Cache de metadatos con TTL configurable (in-memory, 15 min default) | P1 |
| B-RF7 | Cache Redis para producción multi-instancia | P2 |

---

## 8. Módulo C — Capa Semántica de Consumo (Ossie)

### 8.1 Propósito

Apache Ossie es el formato estándar para definir métricas gobernadas y datasets de forma vendor-neutral. ARTOO lo usa como formato de exportación e importación de la capa semántica de consumo.

### 8.2 Por qué Ossie y no un formato propio

- **Estándar Apache**: respaldo de dbt, GoodData, Snowflake, Databricks, Salesforce
- **Multi-dialecto**: cada métrica puede tener `expression` en ANSI_SQL, Snowflake, BigQuery, Databricks
- **AI-ready**: `ai_context.synonyms` y `ai_context.examples` equivalen funcionalmente a `commonQueries`
- **Interoperable**: el mismo YAML puede alimentar Tableau, Power BI, dbt, Looker

### 8.3 Modelo de datos

```yaml
# Ejemplo: modelo semántico de Andorra exportado por el enricher
semantic_model:
  - name: andorra_economy
    description: "Indicadores económicos del Govern d'Andorra"
    ai_context:
      instructions: "Usar para análisis económico y turístico de Andorra"
      synonyms: ["economía andorrana", "PIB Andorra", "turismo Andorra"]
      examples:
        - "¿Qué porcentaje del PIB depende del turismo?"
        - "¿Cómo evolucionó la recaudación fiscal?"

    datasets:
      - name: indicadores_economicos
        source: artoo_demo.public.indicadores_economicos
        primary_key: [anio]
        description: "Indicadores macroeconómicos anuales"
        fields:
          - name: anio
            expression:
              dialects:
                - dialect: ANSI_SQL
                  expression: anio
            datatype: Integer
            dimension:
              is_time: true
          - name: pib_millones_eur
            expression:
              dialects:
                - dialect: ANSI_SQL
                  expression: pib_millones_eur
            datatype: Decimal
            description: "PIB en millones de euros"

    relationships:
      - name: turismo_to_indicadores
        from: turismo
        to: indicadores_economicos
        from_columns: [anio_referencia]
        to_columns: [anio]

    metrics:
      - name: gasto_turistico_total_meur
        expression:
          dialects:
            - dialect: ANSI_SQL
              expression: "SUM(numero_visitantes * gasto_medio_eur) / 1000000"
        description: "Gasto turístico total en millones de euros"
        datatype: Decimal
        ai_context:
          synonyms: ["gasto turismo", "ingresos turísticos"]
          examples:
            - "¿Cuál fue el gasto turístico en 2024?"

      - name: pct_pib_turismo
        expression:
          dialects:
            - dialect: ANSI_SQL
              expression: "SUM(turismo.numero_visitantes * turismo.gasto_medio_eur) / indicadores_economicos.pib_millones_eur / 1000000 * 100"
        description: "Porcentaje del PIB que representa el gasto turístico"
        datatype: Decimal
        ai_context:
          synonyms: ["dependencia turismo", "peso turismo economía"]
          examples:
            - "¿Qué porcentaje del PIB depende del turismo?"

    custom_extensions:
      - vendor_name: OPENMETADATA
        data: '{"fqn": "artoo-postgres.artoo_demo.public.turismo", "pii_tags": [], "sensitivity": "public"}'
```

### 8.4 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| C-RF1 | El enricher genera Ossie YAML por cada asset enriquecido | P1 |
| C-RF2 | Las métricas se infieren a partir de columnas numéricas con tags `UnidadesMedida.*` | P1 |
| C-RF3 | `ai_context.synonyms` se genera a partir de `commonQueries` | P1 |
| C-RF4 | El schema Ossie se valida contra `osi-schema.json` antes de escribir | P1 |
| C-RF5 | Ossie YAML se versiona en `_ossie/<asset_fqn>.yaml` | P1 |
| C-RF6 | Flag `ENABLE_OSSIE_EXPORT` (default: `true`) para desactivar exportación | P1 |
| C-RF7 | Pin de versión de schema Ossie a `0.2.0.dev0` con actualización manual | P1 |
| C-RF8 | `custom_extensions.vendor_name: OPENMETADATA` con referencia al FQN | P1 |

### 8.5 Riesgo: schema inmaduro

Ossie está en versión `0.2.0.dev0` — schema mutable, no production-ready. Mitigación:
- Pin de versión en `config.py`: `OSSIE_SCHEMA_VERSION = "0.2.0.dev0"`
- Módulo `catalog/ossie.py` desactivable con flag
- Actualización de schema como proceso manual con tests

---

## 9. Módulo D — Query Orchestrator

### 9.1 Propósito

Coordinar el flujo de una pregunta en lenguaje natural hasta una respuesta con datos, SQL, explicación y visualización.

### 9.2 Flujo

```
Pregunta en lenguaje natural
       │
  Intent Classifier
  conversational / data_query
       │ data_query
       │
  Source Selector
  semantic_search(question) → OM
  → assets rankeados por relevancia
  → adapter_type ya resuelto
       │
  Query Planner
  agrupa assets por adapter_type
  → genera query por grupo con prompt específico
       │
  ┌────┴────────────────────────┐
  │ (paralelo)                   │
  │ SQL Adapter · Search · Metrics
  └────┬────────────────────────┘
       │ resultados normalizados
  Result Merger
  presenta datasets al LLM
  (NO hace JOIN entre fuentes)
       │
  Explanation + Chart
```

### 9.3 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| D-RF1 | Intent classification con `LLM_INTENT_MODEL` separado | P0 |
| D-RF2 | Source Selector usa semantic search en OM con fallback a todas las tablas | P0 |
| D-RF3 | Validación de columnas con `sqlglot` AST (fail-open para refs sin calificar) | P0 |
| D-RF4 | EXPLAIN dry-run antes de ejecutar SQL | P0 |
| D-RF5 | Retry con feedback de error (máx 1 retry) | P0 |
| D-RF6 | `SourceQueryResponse` model genérico (SQL string o dict para ES DSL) | P0 |
| D-RF7 | Selección de prompt por `query_language` del asset | P0 |
| D-RF8 | Multi-fuente en paralelo con `asyncio.gather` | P1 |
| D-RF9 | Result Merger presenta datasets al LLM sin JOIN estructural | P0 |
| D-RF10 | `source_filter` en `QueryRequest` para filtrar por assets concretos | P1 |

### 9.4 Result Merger — alcance limitado

El Merger NO intenta hacer JOIN entre fuentes heterogéneas. Lo que hace:

- Si una sola fuente responde la pregunta → resultado directo
- Si múltiples fuentes son relevantes → ejecutar en paralelo, presentar resultados lado a lado al LLM de explicación
- El LLM de explicación fusiona **narrativamente**, no estructuralmente

**Ejemplo:** *"¿Cuál fue el impacto del outage de ayer en ingresos?"*
→ Elasticsearch devuelve timeline del outage
→ Snowflake devuelve ingresos por hora
→ El LLM explica la correlación sin hacer JOIN en Python

### 9.5 Prompts por fuente

Cada prompt incluye ejemplos few-shot para reducir alucinación del LLM:

```python
PROMPT_BY_LANGUAGE = {
    "sql_postgres":  QUERY_SYSTEM_PROMPT,        # ya existe en v1
    "sql_snowflake": SNOWFLAKE_QUERY_PROMPT,     # hint QUALIFY, FLATTEN
    "sql_bigquery":  BIGQUERY_QUERY_PROMPT,      # hint STRUCT, UNNEST, backtick
    "es_dsl":        ES_QUERY_SYSTEM_PROMPT,     # genera JSON ES DSL
    "promql":        PROMQL_SYSTEM_PROMPT,       # genera PromQL
    "sql_druid":     DRUID_QUERY_SYSTEM_PROMPT,  # hint TIME_FLOOR, TIME_PARSE
    "duckdb_sql":    QUERY_SYSTEM_PROMPT,        # compatible con postgres
}
```

**Nota sobre Nova Lite:** el modelo base no conoce bien ES DSL ni PromQL. Los prompts deben incluir 2-3 ejemplos few-shot concretos por lenguaje. Ver Apéndice B.

---

## 10. Módulo E — Adaptadores de Fuente

### 10.1 Interfaz común

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
    query_language: str
    supports_joins: bool
    supports_aggregation: bool
    supports_full_text_search: bool
    is_time_series: bool
    time_field: str | None
    supports_dry_run: bool
    max_result_rows: int

class SourceAdapter(Protocol):
    async def execute(self, query: str) -> QueryResult: ...
    async def dry_run(self, query: str) -> str: ...
    def capabilities(self) -> SourceCapabilities: ...
    def query_language_hint(self) -> str: ...
```

### 10.2 Adaptadores por prioridad

| Prioridad | Adaptador | Proyectos | Query language | Complejidad |
|---|---|---|---|---|
| P1 | **Snowflake** | Barceló Hotels | SQL Snowflake | Baja |
| P1 | **Elasticsearch** | MasOrange | ES DSL (JSON) | Media |
| P2 | **BigQuery** | MasOrange | SQL BigQuery | Baja |
| P2 | **Grafana / Prometheus** | Moeve | PromQL | Alta |
| P3 | **Druid** | Moeve | Druid SQL | Media |
| P3 | **Confluent / Kafka** | Piñero · Barceló | Materialización DuckDB | Alta |
| P4 | **MongoDB / DocumentDB** | Teladoc | MQL | Media |
| P4 | **DuckDB** | File-based | SQL DuckDB | Baja |

### 10.3 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| E-RF1 | `PostgreSQLAdapter` migra el código actual a la interfaz común | P0 |
| E-RF2 | `SnowflakeAdapter` con `snowflake-connector-python` y EXPLAIN | P1 |
| E-RF3 | `ElasticsearchAdapter` con `elasticsearch-py` y `/_validate/query` | P1 |
| E-RF4 | `BigQueryAdapter` con `google-cloud-bigquery` y `job.dry_run` | P2 |
| E-RF5 | `PrometheusAdapter` con HTTP API y validación por query instantánea | P2 |
| E-RF6 | `DruidAdapter` con REST API y `EXPLAIN PLAN FOR` | P3 |
| E-RF7 | `ConfluentAdapter` con materialización en DuckDB | P3 |
| E-RF8 | Todos los adaptadores normalizan a `List[Dict[str, Any]]` | P0 |
| E-RF9 | Credenciales por asset via `connection_secret_id` en OM | P2 |
| E-RF10 | Timeout configurable por adaptador (default 30s) | P1 |

### 10.4 Detalle por adaptador

**Snowflake**
- Conexión: `snowflake-connector-python`
- SQL: `QUALIFY`, funciones de ventana, `FLATTEN` para JSON semiestructurado
- Dry-run: `EXPLAIN`

**Elasticsearch**
- Conexión: `elasticsearch-py`
- Query: ES DSL en JSON (el LLM genera dict, no string)
- Dry-run: `/_validate/query`
- Normalización: `hits.hits._source` → `List[Dict]`

**BigQuery**
- Conexión: `google-cloud-bigquery`
- SQL: `STRUCT`, `UNNEST`, backtick quoting
- Dry-run: `job.dry_run = True` → bytes estimados sin ejecutar

**Grafana / Prometheus**
- Conexión: Grafana HTTP API o Prometheus HTTP API
- Query: PromQL
- Dry-run: query con `start=now-1s&end=now` (valida sintaxis sin resultado)
- Normalización: matrix/vector → `List[Dict]` con `timestamp`, `value`, `labels`

**Druid**
- Conexión: Druid SQL REST API (`/druid/v2/sql`)
- SQL: `TIME_FLOOR`, `TIME_PARSE`
- Dry-run: `EXPLAIN PLAN FOR ...`

**Confluent / Kafka**
- No es queryable directamente
- Estrategia PoC: materialización en DuckDB por el enricher
- Estrategia producción: ksqlDB si el cliente lo tiene desplegado

---

## 11. Módulo F — API y Chat

### 11.1 API

El endpoint `POST /api/query` no cambia de contrato externamente:

```python
class QueryRequest(BaseModel):
    question: str
    history: list[ConversationMessage] | None = None
    source_filter: list[str] | None = None  # NUEVO: filtrar por assets
```

Nuevos endpoints de administración:

```
POST /api/admin/refresh-cache/{asset_fqn}   # invalida cache de un asset
GET  /api/admin/sources                     # lista fuentes con estado
GET  /api/admin/sources/{fqn}/schema        # schema cacheado de un asset
GET  /api/admin/ossie/{asset_fqn}           # descarga Ossie YAML del asset
```

### 11.2 Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| F-RF1 | `QueryResponse` con `sql`, `rows`, `explanation`, `chart_type` opcionales | P0 |
| F-RF2 | Respuesta conversacional sin SQL cuando intent = conversational | P0 |
| F-RF3 | Chart recommendation por LLM (`LLM_CHART_MODEL` separado) | P0 |
| F-RF4 | Sidebar con click-to-query (muestra todos los datos de la tabla) | P0 |
| F-RF5 | Historial de conversación con contexto para preguntas de seguimiento | P0 |
| F-RF6 | `source_filter` para limitar query a assets concretos | P1 |
| F-RF7 | Indicador de fuente en la respuesta (badge con nombre del asset) | P1 |
| F-RF8 | Soporte multi-fuente en UI (resultados de varias fuentes lado a lado) | P2 |

---

## 12. Dependencias entre Módulos

```
MÓDULO A (Enricher)
    │
    │ escribe en
    ▼
MÓDULO B (OpenMetadata) ←── MÓDULO C (Ossie YAML)
    │                              │
    │ leído por                    │ leído por
    ▼                              ▼
MÓDULO D (Query Orchestrator)
    │
    │ usa
    ▼
MÓDULO E (Adaptadores)
    │
    │ devuelve a
    ▼
MÓDULO F (API + Chat)
```

| Módulo | Depende de | Bloqueado por |
|---|---|---|
| A — Enricher | OpenMetadata API, LLM, fuente de datos | Nada (es el punto de entrada) |
| B — Catálogo | Módulo A | A |
| C — Ossie | Módulo A (genera el YAML) | A |
| D — Orchestrator | Módulos B + C + E | A, B, E |
| E — Adaptadores | Fuente de datos, credenciales | Nada (independientes entre sí) |
| F — API + Chat | Módulos D + E | Todos |

---

## 13. Fases de Implementación

### Fase 2.0 — Infraestructura base

*Prerequisito de todo lo demás. Sin esta fase, nada funciona.*

- `SourceAdapter` Protocol + `QueryResult` + `SourceCapabilities` (base.py)
- `PostgreSQLAdapter` — migración del código actual a la interfaz común
- `QueryOrchestrator` — refactor de `QueryPipeline` con selección dinámica
- Source Selector — semantic search en OM retorna assets con `adapter_type`
- Result Merger — presenta datasets al LLM sin JOIN estructural
- `SourceQueryResponse` model genérico
- Custom properties en OM (`adapter_type`, `query_language`, `is_time_series`, `time_field`)
- Cache de metadatos in-memory (TTL configurable)
- Tests: `QueryOrchestrator` con dos adaptadores mock en paralelo

**Criterio de aceptación:** una pregunta sobre PostgreSQL funciona end-to-end con la nueva arquitectura, sin regresiones respecto a v1.

### Fase 2.1 — SQL Adapters + Ossie Export

*Objetivo: Barceló Hotels (Snowflake) + MasOrange BigQuery*

- `SnowflakeAdapter` + enricher Snowflake discovery
- `BigQueryAdapter` + enricher BigQuery discovery
- `DuckDBAdapter` (file-based: S3, Parquet, CSV) + enricher file scanner
- `SNOWFLAKE_QUERY_PROMPT` + `BIGQUERY_QUERY_PROMPT` con ejemplos few-shot
- Módulo C: `catalog/ossie.py` — generación de Ossie YAML por asset
- Tests de integración con Snowflake sandbox y BigQuery sandbox

**Criterio de aceptación:** una pregunta sobre Snowflake genera SQL Snowflake correcto y devuelve resultado con chart. El enricher genera Ossie YAML válido para cada asset.

### Fase 2.2 — Search & Logs Adapter

*Objetivo: MasOrange ELK (LOGORA)*

- `ElasticsearchAdapter`
- `ES_QUERY_SYSTEM_PROMPT` con ejemplos few-shot (el LLM genera ES DSL JSON)
- Enricher: Elasticsearch index discovery + field mapping enrichment
- Normalización `hits.hits._source` → `List[Dict]`
- Dry-run vía `/_validate/query`
- Tests de integración con Elasticsearch en Docker

**Criterio de aceptación:** una pregunta como *"¿qué causó el outage ayer?"* genera ES DSL válido, lo ejecuta sobre un índice de test y devuelve resultado.

### Fase 2.3 — Metrics Adapter

*Objetivo: Moeve (Grafana Cloud + Druid)*

- `PrometheusAdapter` + `GrafanaAdapter`
- `PROMQL_SYSTEM_PROMPT` con ejemplos few-shot
- Enricher: Prometheus metric discovery (nombres, labels, tipo)
- Normalización matrix/vector → `List[Dict]` (`timestamp`, `value`, `labels`)
- `DruidAdapter` + `DRUID_QUERY_SYSTEM_PROMPT`
- Tests de integración

**Criterio de aceptación:** una pregunta como *"¿qué turbinas superaron el umbral de vibración?"* genera PromQL válido y devuelve serie temporal con chart de línea.

### Fase 2.4 — Streams Adapter

*Objetivo: Piñero Group + Barceló (Confluent)*

- `ConfluentAdapter` — materialización de topics en DuckDB para consulta
- Enricher: Schema Registry connector (schemas Avro/Protobuf/JSON)
- Cache de materialización con TTL configurable por topic
- Tests con Confluent local (Testcontainers)

**Criterio de aceptación:** un topic de Kafka se materializa automáticamente en DuckDB y las preguntas sobre ese topic se resuelven consultando la materialización.

### Fase 2.5 — Cache Redis + Producción

*Prerequisito para producción con múltiples clientes*

- Redis backend para `AssetCache` (namespace por tenant)
- Invalidación por evento (enricher publica versión → cache compara al leer)
- Rate limiting por tenant en la API
- `connection_secret_id` por asset — cada adaptador resuelve credenciales en runtime

---

## 14. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El LLM genera ES DSL inválido frecuentemente | Media | Alto | Retry con error; fallback a `match_all` filtrado; ejemplos few-shot |
| PromQL es complejo para Nova Lite | Alta | Medio | Ejemplos few-shot; validación con Prometheus antes de ejecutar |
| Ossie schema cambia antes de estabilizar | Media | Medio | Pin de versión `0.2.0.dev0`; flag `ENABLE_OSSIE_EXPORT=false` |
| Kafka no es queryable directamente | Certeza | Alto | Materialización en DuckDB definida en sección 10.4 |
| Latencia alta en Snowflake para exploración | Media | Medio | Cache de resultados frecuentes; LIMIT agresivo por defecto |
| Multi-tenancy: credenciales por cliente | Alta | Alto | `connection_secret_id` por asset en OM; adaptador resuelve en runtime |
| OpenMetadata API cambia entre versiones | Media | Alto | Pin de versión OM 1.5.8; tests de integración por versión |
| commonQueries demasiado técnicas para routing | Media | Alto | LLM enrichment con `business_domain` como contexto de idioma |

---

## 15. Decisiones Pendientes

1. ¿La cache es in-memory siempre o Redis desde el primer sprint?
2. ¿El `QueryOrchestrator` maneja queries multi-fuente o solo mono-fuente en v2?
3. ¿El enricher se ejecuta manualmente o hay un scheduler automático para discovery?
4. ¿Cómo se gestiona la rotación de credenciales de cada adaptador (Secrets Manager, Vault, env vars)?
5. ¿Ossie YAML se guarda como fichero en `_ossie/` o como custom property en OM?
6. ¿El caso de entrada mínimo es PostgreSQL+Snowflake o solo PostgreSQL en Fase 2.0?

---

## 16. Apéndices

### Apéndice A — Configuración

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
GOOGLE_APPLICATION_CREDENTIALS=
BIGQUERY_PROJECT=

# Grafana / Prometheus
GRAFANA_HOST=
GRAFANA_API_KEY=
PROMETHEUS_HOST=

# Druid
DRUID_HOST=

# Ossie
ENABLE_OSSIE_EXPORT=true
OSSIE_SCHEMA_VERSION=0.2.0.dev0
OSSIE_OUTPUT_DIR=./_ossie/

# Cache
METADATA_CACHE_BACKEND=memory
REDIS_URL=redis://localhost:6379/0
METADATA_CACHE_TTL_SECONDS=900

# Enricher
ENRICHMENT_CONCURRENCY=3
SAMPLE_ROWS=5
```

### Apéndice B — Ejemplos few-shot para prompts

**ES_QUERY_SYSTEM_PROMPT — ejemplos:**

```
Ejemplo 1:
  Pregunta: "¿Cuántos errores 500 hubo en la última hora?"
  ES DSL: {
    "query": {
      "bool": {
        "must": [
          { "term": { "status_code": 500 } },
          { "range": { "@timestamp": { "gte": "now-1h" } } }
        ]
      }
    },
    "aggs": { "count": { "value_count": { "field": "status_code" } } }
  }

Ejemplo 2:
  Pregunta: "¿Qué endpoints tienen más errores?"
  ES DSL: {
    "size": 0,
    "aggs": {
      "top_endpoints": {
        "terms": { "field": "endpoint.keyword", "size": 10 }
      }
    }
  }
```

**PROMQL_SYSTEM_PROMPT — ejemplos:**

```
Ejemplo 1:
  Pregunta: "¿Qué turbinas superaron el umbral de vibración esta semana?"
  PromQL: vibration_level > 5.0 and on(instance) (time() - timestamp(vibration_level) < 604800)

Ejemplo 2:
  Pregunta: "¿Cuál es la tasa de error del servicio en las últimas 24 horas?"
  PromQL: rate(http_requests_total{status=~"5.."}[24h]) / rate(http_requests_total[24h])
```

### Apéndice C — Estructura de directorios

```
src/artoo/
├── api/
│   ├── server.py
│   ├── orchestrator.py          (antes pipeline.py)
│   └── validator.py
├── adapters/                    ← NUEVO
│   ├── __init__.py
│   ├── base.py                  (SourceAdapter Protocol)
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
│   ├── ossie.py                 ← NUEVO (generación Ossie YAML)
│   ├── cache.py                 ← NUEVO
│   ├── units.py
│   └── conversion_rules.py
├── enricher/
│   ├── __main__.py
│   ├── enricher.py
│   ├── collector.py
│   ├── writer.py
│   └── sources/                 ← NUEVO
│       ├── elasticsearch.py
│       ├── snowflake.py
│       ├── bigquery.py
│       ├── prometheus.py
│       └── druid.py
├── llm/
│   ├── client.py
│   └── prompts.py               (añadir prompts por fuente)
├── config.py
└── models.py
```

### Apéndice D — Modelo de negocio y coste

- ARTOO corre on-prem o en el cloud del cliente
- Coste = implementación + LLM API (AWS Bedrock, pay per token)
- Sin licencia por usuario
- El enricher corre como batch job — coste LLM proporcional al número de assets
- Referencia: enriquecimiento de 50 tablas ≈ $0.50 en Nova Lite
- Referencia: 1.000 queries/mes ≈ $10 en Nova Lite + explicación con Sonnet

---

*v0.2 — PRD para Spec Driven Development. Sujeto a cambios tras decisiones de arquitectura pendientes (sección 15).*
