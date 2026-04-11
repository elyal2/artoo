# ARTOO: AI-Ready Data Intelligence Platform — Proof of Concept

## Specification Document

**Version:** 1.0
**Date:** April 2026
**Author:** Data Analytics & AI Business Unit — Logicalis España
**Status:** Draft — Ready for implementation

---

## 1. Problem Statement

### 1.1 The Last Mile Problem

Every data engineering project Logicalis delivers — LOGORA (MasOrange), Kora (Barceló), IoT platforms (Moeve), ETL pipelines (Piñero) — creates a data estate the client cannot fully exploit. We build pipelines, integrate sources, model schemas, deploy dashboards. Then someone asks "Show me all customers who had a bad experience in the last 30 days" — and the engineer says "I need 2 hours, a SQL query, and access to 3 systems."

The data is there. The access isn't. Every question requires a specialist, a query language, and knowledge of which table lives where. The business user goes back to asking the data team, the data team is backlogged, and the investment in data infrastructure delivers a fraction of its potential value.

### 1.2 Why It Hasn't Been Solved

Previous approaches to "natural language over databases" failed because the LLM didn't know what the data meant. A column named `rm_cat` could be anything. Sending the raw schema to an LLM produces hallucinated SQL — the model guesses table names, invents columns, and generates queries that either fail or return wrong results.

The missing piece is a **semantic catalog** — a layer that knows not just the structure of the data (tables, columns, types) but its meaning (what each column represents, how tables relate semantically, which fields contain PII, what business domain they belong to). With a semantic catalog as grounding, the LLM stops hallucinating and starts generating correct, explainable queries.

### 1.3 What This PoC Demonstrates

The smallest possible end-to-end implementation of the ARTOO pattern:

1. A **PostgreSQL database** with realistic hotel booking data (the kind any audience understands).
2. **OpenMetadata** auto-crawls the schema — structural discovery in seconds.
3. An **LLM-powered enricher** reads the schema + sample data and generates semantic descriptions, business tags, and PII classifications — writes them back to the catalog.
4. An **AI copilot** receives natural language questions, retrieves semantic context from the catalog, generates grounded SQL, executes it, and returns results with explanations.
5. A **chat interface** where the demo audience types questions and sees the magic happen.

The demo narrative is a before/after:
- **Before ARTOO:** Open Superset, write SQL manually, need to know the schema, takes minutes per question.
- **After ARTOO:** Open the chat, ask in plain English, get the answer in seconds — with the SQL shown for transparency.

---

## 2. Solution Philosophy

### 2.1 Core Principles

**Connect, don't build.** ARTOO doesn't create new data infrastructure. It connects to what already exists. The client's PostgreSQL/BigQuery/Confluent/ELK stays untouched. ARTOO adds intelligence on top.

**Crawl, don't configure.** OpenMetadata's auto-discovery eliminates manual schema documentation. Point it at a data source, it crawls. The LLM enricher handles the semantic gap automatically — no human needs to write descriptions for 500 columns.

**Ground, don't hallucinate.** Every LLM query is grounded in the semantic catalog. The LLM never guesses table names or column types — it reads them from OpenMetadata. If a column isn't in the catalog, it doesn't exist in the LLM's world.

**Cloud-agnostic, always.** The PoC uses PostgreSQL, but the pattern works identically on BigQuery, Snowflake, Confluent, ELK, or any of OpenMetadata's 50+ connectors. The LLM provider is configurable (Claude, GPT, Gemini, local models).

### 2.2 Relationship to the Full Platform

| Full Platform Component | PoC Equivalent |
|---|---|
| Client's data estate (BigQuery, Confluent, ELK...) | PostgreSQL with demo data |
| Semantic Catalog (OpenMetadata) | OpenMetadata (same) |
| PII Detection (Presidio) | LLM-based classification in enricher |
| Data Lineage (OpenLineage) | Not implemented (Tier 2) |
| AI Copilot (LLM + RAG) | artoo-api (FastMCP + LLM) |
| Chat interface | artoo-chat (minimal React/HTML) |
| Governance (RBAC, audit) | Not implemented (Tier 2) |

### 2.3 Relationship to SOLO

ARTOO and SOLO are independent solutions with different entry points:

| | SOLO | ARTOO |
|---|---|---|
| Starting point | A live incident | A question |
| What it does | Detects, diagnoses, remediates | Catalogs, enriches, queries |
| Deployment model | Build for the client (months) | Connect to what they have (weeks) |
| Core technology | LangGraph + Digital Twin + MCP | OpenMetadata + LLM + RAG |
| Entry point | NOC / network operations | Any data engineering project |

They share the same engagement model (Professional Services + Managed Service + Enablement) and the same España/Local split, but they serve different buyers and different pain points.

---

## 3. Architecture

### 3.1 Services (Docker Compose)

```
┌─────────────────────────────────────────────────────────┐
│  docker compose                                         │
│                                                         │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ postgres   │  │ openmetadata │  │ superset         │  │
│  │ Demo data  │  │ Catalog +    │  │ "The Before"     │  │
│  │ 10K rows   │  │ Semantic     │  │ Manual SQL       │  │
│  │            │  │ Search       │  │                  │  │
│  └───────────┘  └──────────────┘  └──────────────────┘  │
│                                                         │
│  ┌───────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ artoo-enricher │  │ artoo-api  │  │ artoo-chat     │  │
│  │ LLM semantic   │  │ FastMCP    │  │ "The After"    │  │
│  │ enrichment     │  │ NL → SQL   │  │ NL chat UI     │  │
│  │ (batch job)    │  │ → execute  │  │                │  │
│  └───────────────┘  └────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**`postgres`** — PostgreSQL 16 with a pre-seeded hotel booking database. 6 tables, 10K+ rows, realistic data. Deliberately uses cryptic column names to demonstrate the enricher's value.

**`openmetadata`** — OpenMetadata server (official Docker image). Includes its internal dependencies (Elasticsearch for search, MySQL for metadata storage). Configured to auto-crawl PostgreSQL on startup.

**`superset`** — Apache Superset connected to the same PostgreSQL. Used in the demo as the "before" — the manual SQL experience. Optional: can be replaced with Metabase or even pgAdmin if simplicity is preferred.

**`artoo-enricher`** — Python batch job that runs after OpenMetadata's crawl completes. Reads the raw schema from OpenMetadata API, samples data from PostgreSQL, sends both to the LLM, and writes semantic descriptions + tags back to OpenMetadata. Runs once, then exits.

**`artoo-api`** — FastAPI application exposing MCP-compatible endpoints. Receives NL questions, retrieves semantic context from OpenMetadata, builds a grounded prompt, calls the LLM, extracts the generated SQL, executes it against PostgreSQL (read-only), and returns the result + explanation.

**`artoo-chat`** — Minimal web frontend (single HTML file or React component) with a chat interface. Sends questions to artoo-api, displays the answer, the generated SQL, and the data table.

### 3.2 Data Flow

```
User types question
       │
       ▼
  artoo-chat (frontend)
       │
       ▼ POST /query {question: "..."}
  artoo-api (FastMCP)
       │
       ├──► OpenMetadata API: get relevant tables + semantic descriptions
       │    (Semantic Search over catalog embeddings)
       │
       ├──► LLM API: generate SQL grounded in catalog context
       │    (Claude / GPT / Gemini via env var)
       │
       ├──► PostgreSQL: execute generated SQL (read-only)
       │
       ▼
  Return to frontend:
    - Natural language answer
    - Generated SQL (for transparency)
    - Result table (rows)
    - Source tables used (from catalog)
```

---

## 4. Module Specifications

### 4.1 PostgreSQL Demo Database

**Responsibility:** Provide a realistic data estate with intentionally cryptic naming to demonstrate the enricher's value.

**Schema design — `hotel_demo` database:**

```sql
-- Customers table (cryptic names on purpose)
CREATE TABLE cust (
    cust_id SERIAL PRIMARY KEY,
    cust_fname VARCHAR(50) NOT NULL,
    cust_lname VARCHAR(50) NOT NULL,
    cust_email VARCHAR(100),
    cust_phone VARCHAR(20),
    cust_dob DATE,
    cust_nat VARCHAR(3),         -- nationality ISO code
    cust_tier VARCHAR(10),       -- loyalty tier: BRZ/SLV/GLD/PLT
    cust_created TIMESTAMP DEFAULT now()
);

-- Properties
CREATE TABLE prop (
    prop_id SERIAL PRIMARY KEY,
    prop_name VARCHAR(100) NOT NULL,
    prop_city VARCHAR(50),
    prop_country VARCHAR(3),
    prop_stars INT,
    prop_rooms INT,
    prop_type VARCHAR(20)        -- RESORT/URBAN/BOUTIQUE
);

-- Room categories
CREATE TABLE rm_cat (
    cat_id SERIAL PRIMARY KEY,
    cat_code VARCHAR(5),          -- STD/SUP/DLX/STE/PRS
    cat_name VARCHAR(50),
    cat_base_rate DECIMAL(10,2),
    cat_max_occ INT
);

-- Bookings
CREATE TABLE bkng (
    bk_id SERIAL PRIMARY KEY,
    cust_id INT REFERENCES cust(cust_id),
    prop_id INT REFERENCES prop(prop_id),
    cat_id INT REFERENCES rm_cat(cat_id),
    dt_chkin DATE NOT NULL,
    dt_chkout DATE NOT NULL,
    n_guests INT,
    tot_amt DECIMAL(10,2),
    pay_meth VARCHAR(10),         -- VISA/AMEX/MC/CASH/BNKXFR
    bk_status VARCHAR(10),        -- CONF/CNCL/NOSH/COMP
    bk_channel VARCHAR(10),       -- WEB/APP/OTA/PHONE/WALKIN
    bk_created TIMESTAMP DEFAULT now()
);

-- Guest experiences / surveys
CREATE TABLE gx (
    gx_id SERIAL PRIMARY KEY,
    bk_id INT REFERENCES bkng(bk_id),
    nps_score INT,                -- 0-10
    ov_rating INT,                -- 1-5 overall
    clean_rating INT,             -- 1-5 cleanliness
    svc_rating INT,               -- 1-5 service
    fb_text TEXT,                  -- free text feedback
    gx_date DATE
);

-- Revenue daily aggregates
CREATE TABLE rev_daily (
    rev_id SERIAL PRIMARY KEY,
    prop_id INT REFERENCES prop(prop_id),
    rev_date DATE,
    occ_pct DECIMAL(5,2),         -- occupancy %
    adr DECIMAL(10,2),            -- average daily rate
    revpar DECIMAL(10,2),         -- revenue per available room
    n_checkins INT,
    n_checkouts INT,
    n_cancellations INT
);
```

**Seed data:**

A Python script (`seed.py`) generates:
- 2,000 customers across 15 nationalities, 4 loyalty tiers
- 12 properties across 6 cities (Barcelona, Madrid, Lisbon, Mexico City, London, Dubai)
- 5 room categories with realistic pricing
- 10,000 bookings spanning 2023-2026 with seasonal patterns
- 6,000 guest experiences with realistic NPS distribution (detractors/passives/promoters)
- 730 days of revenue aggregates per property

The data is realistic enough that queries return meaningful answers: "Which property has the highest cancellation rate?" actually has an answer. "Show me promoter customers who haven't returned" produces a meaningful list.

**Why cryptic names:** The entire point of the demo is to show that ARTOO makes cryptic schemas queryable. If we name everything `customer_first_name`, the enricher has nothing to demonstrate. The cryptic names force the enricher to prove its value.

### 4.2 OpenMetadata

**Responsibility:** Auto-discover the PostgreSQL schema and provide a semantic catalog with Semantic Search.

**Deployment:** Official Docker Compose from OpenMetadata (includes server, Elasticsearch, MySQL). We add a PostgreSQL connector configuration via the OpenMetadata API on startup.

**Startup sequence:**

1. OpenMetadata server starts (takes ~60s)
2. A bootstrap script (`bootstrap-openmetadata.py`) waits for the server to be healthy
3. Creates a PostgreSQL service connection via API:
```python
# POST /api/v1/services/databaseServices
{
    "name": "hotel-demo-postgres",
    "serviceType": "Postgres",
    "connection": {
        "config": {
            "type": "Postgres",
            "hostPort": "postgres:5432",
            "database": "hotel_demo",
            "username": "artoo_readonly",
            "password": "${POSTGRES_PASSWORD}",
            "scheme": "postgresql+psycopg2"
        }
    }
}
```
4. Triggers an ingestion workflow:
```python
# POST /api/v1/services/ingestionPipelines
{
    "name": "hotel-demo-metadata-ingestion",
    "pipelineType": "metadata",
    "service": {"id": "<service-id>"},
    "sourceConfig": {
        "config": {
            "type": "DatabaseMetadata",
            "markDeletedTables": true,
            "includeTables": true,
            "includeViews": true
        }
    }
}
```
5. OpenMetadata crawls PostgreSQL: discovers 6 tables, all columns, types, FKs, constraints
6. Semantic Search indexes the raw metadata (schema names, column names)

**After crawl, before enrichment:** OpenMetadata knows that `cust.cust_dob` is a `DATE` column with a foreign key to nothing. It does NOT know it means "Customer Date of Birth." That's the enricher's job.

**Configuration:**

| Env Var | Type | Default | Description |
|---|---|---|---|
| `OPENMETADATA_URL` | `str` | `http://openmetadata:8585` | OM server URL |
| `OPENMETADATA_API_TOKEN` | `str` | — | Admin API token (generated on first boot) |

### 4.3 Enricher (`artoo-enricher/`)

**Responsibility:** Bridge the gap between structural metadata (what OpenMetadata crawls) and semantic metadata (what the LLM needs to generate correct SQL). This is the core IP of ARTOO.

#### 4.3.1 Three-Stage Enrichment Pipeline

**Stage 1 — Schema + Sample Data Collection:**

```python
class SchemaCollector:
    """Reads raw schema from OpenMetadata, samples data from PostgreSQL."""

    async def collect(self, table_fqn: str) -> TableContext:
        # 1. Get table metadata from OpenMetadata
        table = await self.om_client.get_table(table_fqn)

        # 2. Sample 5 rows from PostgreSQL
        sample_query = f"SELECT * FROM {table.name} ORDER BY RANDOM() LIMIT 5"
        sample_rows = await self.pg_client.fetch(sample_query)

        # 3. Get FK relationships
        fk_info = [
            f"{col.name} → {col.fk_table}.{col.fk_column}"
            for col in table.columns if col.foreign_key
        ]

        # 4. Get column statistics (min, max, distinct count, null %)
        stats = await self._compute_column_stats(table.name, table.columns)

        return TableContext(
            name=table.name,
            columns=table.columns,
            sample_rows=sample_rows,
            foreign_keys=fk_info,
            column_stats=stats,
            row_count=await self._count_rows(table.name),
        )
```

**Stage 2 — LLM Semantic Inference:**

```python
class SemanticEnricher:
    """Uses LLM to generate semantic descriptions from schema + data."""

    async def enrich(self, context: TableContext) -> TableEnrichment:
        prompt = self._build_prompt(context)
        response = await self.llm_client.complete(
            system=ENRICHMENT_SYSTEM_PROMPT,
            user=prompt,
        )
        return TableEnrichment.model_validate_json(response)
```

**The enrichment prompt:**

```python
ENRICHMENT_SYSTEM_PROMPT = """
You are a data catalog specialist. You analyze database schemas and sample
data to generate accurate semantic descriptions.

You receive: table name, column definitions (name, type, constraints),
foreign key relationships, 5 sample rows, and basic statistics.

You respond with a JSON object containing:
{
  "table_description": "Clear business description of what this table represents",
  "business_domain": "The business area (e.g., 'customer', 'booking', 'revenue', 'feedback')",
  "columns": {
    "<column_name>": {
      "description": "What this column means in business terms",
      "business_name": "Human-readable name (e.g., 'Customer Date of Birth')",
      "pii": true/false,
      "pii_type": "name|email|phone|dob|national_id|null",
      "sensitivity": "public|internal|confidential|restricted",
      "example_values": "2-3 representative values from sample data"
    }
  },
  "suggested_tags": ["tag1", "tag2"],
  "common_queries": [
    "Natural language questions this table can answer"
  ]
}

Rules:
- Infer meaning from column names, data types, sample values, and context
- Mark PII conservatively — when in doubt, flag it
- The business_name should be what a non-technical user would call this field
- common_queries should be realistic questions a business user would ask
- Be specific, not generic. "Customer" is too vague; "Hotel guest who has made a booking" is better
"""
```

**Example input/output for `bkng` table:**

Input sent to LLM:
```
Table: bkng
Columns:
  - bk_id (serial, PK)
  - cust_id (int, FK → cust.cust_id)
  - prop_id (int, FK → prop.prop_id)
  - cat_id (int, FK → rm_cat.cat_id)
  - dt_chkin (date, NOT NULL)
  - dt_chkout (date, NOT NULL)
  - n_guests (int)
  - tot_amt (decimal)
  - pay_meth (varchar)
  - bk_status (varchar)
  - bk_channel (varchar)
  - bk_created (timestamp)

Sample data:
| bk_id | cust_id | prop_id | cat_id | dt_chkin   | dt_chkout  | n_guests | tot_amt | pay_meth | bk_status | bk_channel | bk_created          |
| 1     | 423     | 3       | 2      | 2025-03-15 | 2025-03-18 | 2        | 672.00  | VISA     | CONF      | WEB        | 2025-02-28 14:22:00 |
| 2     | 891     | 1       | 4      | 2025-04-01 | 2025-04-05 | 1        | 1420.00 | AMEX     | COMP      | APP        | 2025-03-15 09:10:00 |
...

Foreign keys: cust_id → cust.cust_id, prop_id → prop.prop_id, cat_id → rm_cat.cat_id
Row count: 10,247
Stats: bk_status distinct values: CONF(7821), CNCL(1203), NOSH(412), COMP(811)
```

LLM response:
```json
{
  "table_description": "Hotel booking records. Each row represents a reservation made by a guest at a specific property, including dates, room category, payment, and booking status.",
  "business_domain": "booking",
  "columns": {
    "bk_id": {
      "description": "Unique booking identifier",
      "business_name": "Booking ID",
      "pii": false, "pii_type": null, "sensitivity": "internal",
      "example_values": "1, 2, 3..."
    },
    "dt_chkin": {
      "description": "Guest check-in date at the hotel",
      "business_name": "Check-in Date",
      "pii": false, "pii_type": null, "sensitivity": "internal",
      "example_values": "2025-03-15, 2025-04-01"
    },
    "bk_status": {
      "description": "Current status of the booking. CONF = Confirmed, CNCL = Cancelled, NOSH = No-show, COMP = Completed",
      "business_name": "Booking Status",
      "pii": false, "pii_type": null, "sensitivity": "internal",
      "example_values": "CONF, CNCL, NOSH, COMP"
    },
    "pay_meth": {
      "description": "Payment method used for the booking",
      "business_name": "Payment Method",
      "pii": false, "pii_type": null, "sensitivity": "internal",
      "example_values": "VISA, AMEX, MC, CASH, BNKXFR"
    }
  },
  "suggested_tags": ["booking", "reservation", "revenue", "operations"],
  "common_queries": [
    "How many bookings were cancelled last month?",
    "What is the average booking value by room category?",
    "Which channel generates the most revenue?",
    "Show me no-show rates by property"
  ]
}
```

**Stage 3 — Write-Back to OpenMetadata:**

```python
class CatalogWriter:
    """Writes enrichment results back to OpenMetadata via API."""

    async def write(self, table_fqn: str, enrichment: TableEnrichment) -> None:
        # 1. Update table description
        await self.om_client.patch_table(table_fqn, {
            "description": enrichment.table_description,
            "tags": [{"tagFQN": f"Business.{t}"} for t in enrichment.suggested_tags],
        })

        # 2. Update each column description + tags
        for col_name, col_info in enrichment.columns.items():
            patch = {
                "description": col_info.description,
                "displayName": col_info.business_name,
            }
            if col_info.pii:
                patch["tags"] = [{"tagFQN": f"PII.{col_info.pii_type.capitalize()}"}]

            await self.om_client.patch_column(table_fqn, col_name, patch)

        # 3. Log enrichment result
        logger.info(
            "Table enriched",
            table=table_fqn,
            columns_enriched=len(enrichment.columns),
            pii_columns=[c for c, i in enrichment.columns.items() if i.pii],
        )
```

#### 4.3.2 Enrichment Report

After processing all tables, the enricher produces a structured report:

```json
{
  "timestamp": "2026-04-12T10:32:00Z",
  "tables_processed": 6,
  "columns_enriched": 42,
  "pii_columns_detected": 4,
  "pii_details": [
    {"table": "cust", "column": "cust_email", "type": "email"},
    {"table": "cust", "column": "cust_phone", "type": "phone"},
    {"table": "cust", "column": "cust_dob", "type": "dob"},
    {"table": "cust", "column": "cust_fname", "type": "name"}
  ],
  "llm_tokens_used": {"input": 4200, "output": 3800},
  "duration_seconds": 45
}
```

#### 4.3.3 Configuration

| Env Var | Type | Default | Description |
|---|---|---|---|
| `OPENMETADATA_URL` | `str` | `http://openmetadata:8585` | OM API URL |
| `POSTGRES_DSN` | `str` | — | PostgreSQL connection string |
| `LLM_PROVIDER` | `str` | `anthropic` | LLM provider |
| `LLM_MODEL` | `str` | `claude-sonnet-4-20250514` | Model for enrichment |
| `LLM_API_KEY` | `str` | — | API key |
| `SAMPLE_ROWS` | `int` | `5` | Rows to sample per table |
| `ENRICHMENT_CONCURRENCY` | `int` | `3` | Tables to enrich in parallel |

### 4.4 API (`artoo-api/`)

**Responsibility:** Receive natural language questions, ground them in the semantic catalog, generate SQL, execute it, and return structured results.

#### 4.4.1 Query Pipeline

```python
class QueryPipeline:
    """NL question → semantic context → LLM → SQL → execute → response."""

    async def query(self, question: str) -> QueryResponse:
        # Step 1: Search catalog for relevant tables
        relevant_tables = await self.catalog.semantic_search(
            query=question,
            n_results=5,
        )

        # Step 2: Build grounded context from catalog
        context = self._build_schema_context(relevant_tables)

        # Step 3: Generate SQL via LLM
        sql_response = await self.llm_client.complete(
            system=QUERY_SYSTEM_PROMPT,
            user=self._build_query_prompt(question, context),
        )
        parsed = SQLResponse.model_validate_json(sql_response)

        # Step 4: Validate SQL (basic safety checks)
        self._validate_sql(parsed.sql)

        # Step 5: Execute against PostgreSQL (read-only connection)
        rows = await self.pg_client.fetch(parsed.sql, timeout=10)

        # Step 6: Generate natural language explanation
        explanation = await self.llm_client.complete(
            system="Explain this SQL query result in plain language.",
            user=f"Question: {question}\nSQL: {parsed.sql}\nResults: {rows[:10]}",
        )

        return QueryResponse(
            question=question,
            sql=parsed.sql,
            explanation=explanation,
            rows=rows[:100],  # cap at 100 rows
            tables_used=parsed.tables_used,
            confidence=parsed.confidence,
        )
```

#### 4.4.2 Query System Prompt

```python
QUERY_SYSTEM_PROMPT = """
You are a SQL expert that generates PostgreSQL queries from natural language
questions. You ONLY use tables and columns that exist in the provided schema.

Rules:
1. ONLY use tables and columns from the schema provided below. Never invent.
2. Use the business descriptions to understand what each column means.
3. Pay attention to coded values (e.g., bk_status: CONF=Confirmed, CNCL=Cancelled).
4. Always use proper JOINs based on foreign key relationships.
5. For date filters, use PostgreSQL date functions.
6. Add LIMIT 100 unless the user specifically asks for all results.
7. Never generate INSERT, UPDATE, DELETE, DROP, or any write operation.

Respond with JSON:
{
  "sql": "SELECT ...",
  "tables_used": ["table1", "table2"],
  "confidence": "high|medium|low",
  "reasoning": "Brief explanation of why you chose these tables and joins"
}
"""
```

#### 4.4.3 Schema Context Builder

The context builder formats the semantic catalog for the LLM prompt:

```python
def _build_schema_context(self, tables: list[CatalogTable]) -> str:
    context_parts: list[str] = []
    for table in tables:
        lines = [f"TABLE: {table.name} — {table.description}"]
        lines.append(f"Business domain: {table.business_domain}")
        lines.append("COLUMNS:")
        for col in table.columns:
            col_line = f"  - {col.name} ({col.type})"
            if col.business_name:
                col_line += f" — {col.business_name}"
            if col.description:
                col_line += f": {col.description}"
            if col.example_values:
                col_line += f" [examples: {col.example_values}]"
            lines.append(col_line)
        if table.foreign_keys:
            lines.append("RELATIONSHIPS:")
            for fk in table.foreign_keys:
                lines.append(f"  - {fk}")
        context_parts.append("\n".join(lines))
    return "\n\n".join(context_parts)
```

Example output sent to LLM:
```
TABLE: bkng — Hotel booking records. Each row represents a reservation
made by a guest at a specific property.
Business domain: booking
COLUMNS:
  - bk_id (serial) — Booking ID: Unique booking identifier
  - cust_id (int) — Customer ID: Reference to the guest
  - dt_chkin (date) — Check-in Date: Guest check-in date at the hotel
  - bk_status (varchar) — Booking Status: CONF=Confirmed, CNCL=Cancelled,
    NOSH=No-show, COMP=Completed [examples: CONF, CNCL, NOSH, COMP]
  - bk_channel (varchar) — Booking Channel [examples: WEB, APP, OTA, PHONE]
RELATIONSHIPS:
  - cust_id → cust.cust_id
  - prop_id → prop.prop_id
```

Without the enricher, this context would be:
```
TABLE: bkng
COLUMNS:
  - bk_id (serial)
  - cust_id (int)
  - dt_chkin (date)
  - bk_status (varchar)
  - bk_channel (varchar)
```

The LLM would have no idea what `bk_status = 'CNCL'` means.

#### 4.4.4 SQL Validation

```python
def _validate_sql(self, sql: str) -> None:
    """Safety checks before executing LLM-generated SQL."""
    sql_upper = sql.upper().strip()

    # Block write operations
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
                 "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"]
    for keyword in forbidden:
        if keyword in sql_upper.split():
            raise SQLValidationError(f"Write operation not allowed: {keyword}")

    # Must start with SELECT or WITH (CTE)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        raise SQLValidationError("Only SELECT queries are allowed")

    # Enforce LIMIT
    if "LIMIT" not in sql_upper:
        sql += " LIMIT 100"
```

#### 4.4.5 FastMCP Endpoints

```python
# MCP-compatible tool definitions
@mcp_server.tool("query_data")
async def query_data(question: str) -> QueryResponse:
    """Ask a question about the data in natural language."""
    return await pipeline.query(question)

@mcp_server.tool("list_tables")
async def list_tables() -> list[TableSummary]:
    """List all available tables with their descriptions."""
    return await catalog.list_tables()

@mcp_server.tool("describe_table")
async def describe_table(table_name: str) -> TableDetail:
    """Get detailed description of a table including all columns."""
    return await catalog.get_table(table_name)

# Also exposed as REST for the chat frontend
app = FastAPI()

@app.post("/api/query")
async def api_query(req: QueryRequest) -> QueryResponse:
    return await pipeline.query(req.question)

@app.get("/api/tables")
async def api_tables() -> list[TableSummary]:
    return await catalog.list_tables()

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

#### 4.4.6 Configuration

| Env Var | Type | Default | Description |
|---|---|---|---|
| `OPENMETADATA_URL` | `str` | `http://openmetadata:8585` | Catalog API |
| `POSTGRES_DSN` | `str` | — | Read-only PostgreSQL connection |
| `LLM_PROVIDER` | `str` | `anthropic` | LLM provider |
| `LLM_MODEL` | `str` | `claude-sonnet-4-20250514` | Model for query generation |
| `LLM_API_KEY` | `str` | — | API key |
| `API_PORT` | `int` | `8000` | FastAPI port |
| `QUERY_TIMEOUT_SECONDS` | `int` | `10` | Max SQL execution time |
| `MAX_RESULT_ROWS` | `int` | `100` | Max rows returned |

### 4.5 Chat Frontend (`artoo-chat/`)

**Responsibility:** Minimal web UI for the demo. Not a product — a demo interface.

**Implementation:** Single HTML file with inline JS (no build step, no npm). Served by artoo-api via FastAPI's `StaticFiles`.

**Features:**
- Text input for natural language questions
- Expandable section showing the generated SQL
- Results displayed as a formatted table
- Source tables listed with links to OpenMetadata
- Confidence indicator (high/medium/low)
- Conversation history (in-memory, not persisted)
- 3-4 suggested questions as quick-start buttons

**Suggested questions (pre-loaded):**
```
"Which properties have the highest cancellation rate?"
"Show me our top 10 customers by total spend who haven't visited in 6 months"
"What is the average NPS score by property and room category?"
"How does weekend occupancy compare to weekday across all properties?"
```

### 4.6 Superset (optional)

**Responsibility:** The "before" experience in the demo. Shows how data access works today — manual SQL, dashboard building, query language expertise required.

**Deployment:** Official Superset Docker image. Pre-configured with the PostgreSQL connection and 1-2 sample dashboards (occupancy trends, revenue by property).

Can be replaced with Metabase or pgAdmin if preferred. The point is to show "the old way" for 60 seconds before switching to the chat.

---

## 5. Project Structure

```
artoo-poc/
├── pyproject.toml
├── uv.lock
├── Makefile
├── docker-compose.yml
├── .env.example
├── .env.local                        # gitignored
├── .pre-commit-config.yaml
├── _docs/
│   └── c4-context.mermaid
├── postgres/
│   ├── init.sql                      # Schema DDL
│   └── seed.py                       # Data generation script
├── openmetadata/
│   └── bootstrap.py                  # Connector + ingestion setup
├── src/
│   └── artoo/
│       ├── __init__.py
│       ├── config.py                 # pydantic-settings
│       ├── models.py                 # Shared domain models
│       ├── logging.py                # Structured JSON logging
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py             # Provider-agnostic LLM client
│       │   └── prompts.py            # All prompt templates
│       ├── catalog/
│       │   ├── __init__.py
│       │   └── openmetadata.py       # OpenMetadata API client
│       ├── enricher/
│       │   ├── __init__.py
│       │   ├── collector.py          # Schema + sample data collection
│       │   ├── enricher.py           # LLM semantic inference
│       │   ├── writer.py             # Write-back to OpenMetadata
│       │   └── __main__.py           # CLI: uv run python -m artoo.enricher
│       ├── api/
│       │   ├── __init__.py
│       │   ├── pipeline.py           # NL → catalog → LLM → SQL → result
│       │   ├── validator.py          # SQL safety validation
│       │   ├── mcp.py                # FastMCP tool definitions
│       │   └── server.py             # FastAPI app + static files
│       └── chat/
│           └── index.html            # Single-file chat frontend
└── tests/
    ├── conftest.py
    ├── test_enricher.py
    ├── test_pipeline.py
    ├── test_validator.py
    └── test_catalog.py
```

---

## 6. Infrastructure

### 6.1 `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: hotel_demo
      POSTGRES_USER: artoo
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/01-schema.sql
      - pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U artoo -d hotel_demo"]
      interval: 5s
      retries: 5

  openmetadata:
    image: openmetadata/server:latest
    environment:
      OPENMETADATA_CLUSTER_NAME: artoo-demo
    ports:
      - "8585:8585"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - om-data:/opt/openmetadata/data

  superset:
    image: apache/superset:latest
    ports:
      - "8088:8088"
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      SUPERSET_SECRET_KEY: ${SUPERSET_SECRET_KEY:-artoo-demo-key}

  artoo-enricher:
    build:
      context: .
      target: enricher
    env_file: .env.local
    depends_on:
      openmetadata:
        condition: service_healthy
    restart: "no"  # Run once, then exit

  artoo-api:
    build:
      context: .
      target: api
    env_file: .env.local
    ports:
      - "8000:8000"
    depends_on:
      openmetadata:
        condition: service_healthy
      postgres:
        condition: service_healthy

volumes:
  pg-data:
  om-data:
```

### 6.2 `Makefile`

```makefile
.PHONY: demo seed enrich test lint

demo: ## Full demo: start everything, seed, crawl, enrich
	docker compose up -d postgres openmetadata superset
	@echo "Waiting for OpenMetadata..."
	sleep 60
	uv run python postgres/seed.py
	uv run python openmetadata/bootstrap.py
	@echo "Waiting for crawl to complete..."
	sleep 30
	docker compose up artoo-enricher
	docker compose up -d artoo-api
	@echo ""
	@echo "╔══════════════════════════════════════════╗"
	@echo "║  ARTOO Demo Ready!                       ║"
	@echo "║                                          ║"
	@echo "║  Chat:           http://localhost:8000    ║"
	@echo "║  OpenMetadata:   http://localhost:8585    ║"
	@echo "║  Superset:       http://localhost:8088    ║"
	@echo "║  PostgreSQL:     localhost:5432           ║"
	@echo "╚══════════════════════════════════════════╝"

seed: ## Re-seed PostgreSQL with fresh demo data
	uv run python postgres/seed.py

enrich: ## Re-run the semantic enricher
	docker compose up artoo-enricher

test: ## Run tests
	uv run pytest -m unit --cov=src/artoo

lint: ## Lint + format + typecheck
	uv run ruff check . --fix
	uv run ruff format .
	uv run mypy src/

down: ## Stop everything
	docker compose down -v
```

### 6.3 `.env.example`

```bash
# LLM
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
LLM_API_KEY=sk-ant-xxxxxxxxxxxx

# PostgreSQL
POSTGRES_PASSWORD=artoo-demo-2026
POSTGRES_DSN=postgresql+psycopg2://artoo:artoo-demo-2026@postgres:5432/hotel_demo

# OpenMetadata
OPENMETADATA_URL=http://openmetadata:8585
OPENMETADATA_API_TOKEN=

# API
API_PORT=8000
QUERY_TIMEOUT_SECONDS=10

# Enricher
SAMPLE_ROWS=5
ENRICHMENT_CONCURRENCY=3

# Observability
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 7. Demo Script (5 minutes)

### Minute 0-1: "The Before"

Open Superset at `localhost:8088`. Show the PostgreSQL tables. Write a SQL query:

```sql
SELECT p.prop_name, COUNT(*) as cancellations,
       ROUND(COUNT(*)::numeric / total.t * 100, 1) as cancel_rate
FROM bkng b
JOIN prop p ON b.prop_id = p.prop_id
CROSS JOIN (SELECT COUNT(*) as t FROM bkng) total
WHERE b.bk_status = 'CNCL'
GROUP BY p.prop_name, total.t
ORDER BY cancel_rate DESC;
```

Say: "This took me 2 minutes to write. I needed to know the table names, the column names, that 'CNCL' means cancelled, and how to join. Your client's engineers do this 50 times a day."

### Minute 1-2: "The Catalog"

Open OpenMetadata at `localhost:8585`. Show the `bkng` table. Point out:
- Automatically crawled from PostgreSQL
- LLM-enriched descriptions: `bk_status` now says "CONF=Confirmed, CNCL=Cancelled, NOSH=No-show, COMP=Completed"
- PII tags on `cust_email`, `cust_phone`, `cust_dob`
- Semantic Search: type "cancellation" → finds `bkng` table immediately

Say: "The enricher understood that `bk_status = 'CNCL'` means cancelled. That `dt_chkin` is check-in date. That `cust_email` is PII. All automatic, no human configuration."

### Minute 2-5: "The After"

Open the chat at `localhost:8000`. Ask:

**Query 1:** "Which properties have the highest cancellation rate?"
→ Shows the same result as the manual SQL, but generated in 3 seconds from a natural language question.

**Query 2:** "Show me our top 10 customers by total spend who haven't returned in 6 months"
→ Complex query with subquery, date math, and JOIN. Would take 5+ minutes to write manually.

**Query 3:** "What is the average NPS score by property? Which one has the most detractors?"
→ Cross-table analysis (bookings + experiences + properties). Shows the LLM understands NPS semantics (0-6 = detractor, 7-8 = passive, 9-10 = promoter).

**Query 4:** "Compare weekend vs weekday occupancy across all properties"
→ Date function usage, aggregation, comparison. Impressive visual result.

Close with: "Same interface, any data domain. Replace this hotel database with your client's Confluent topics, their BigQuery tables, their ELK indices. The pattern is identical. Connect, crawl, query."

---

## 8. Testing Strategy

### 8.1 Unit Tests

- **`test_enricher.py`** — Mock LLM responses. Verify that enrichment JSON is correctly parsed, PII is detected, write-back payloads are well-formed.
- **`test_pipeline.py`** — Mock catalog + LLM + PostgreSQL. Verify end-to-end query flow: NL question → context assembly → SQL generation → execution → response formatting.
- **`test_validator.py`** — Test SQL validation: ensure write operations are blocked, LIMIT is enforced, edge cases (CTEs, subqueries) are handled.
- **`test_catalog.py`** — Mock OpenMetadata API. Verify semantic search calls, table metadata parsing, column enrichment formatting.

### 8.2 Integration Tests

- **`test_full_flow.py`** — Requires PostgreSQL + OpenMetadata running. Seed data, run enricher, execute 10 predefined NL queries, verify results match expected answers.

### 8.3 Coverage Target

80% on `enricher/`, `api/pipeline.py`, `api/validator.py`. No coverage hunting on infrastructure glue.

---

## 9. Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pydantic` | ≥2.0 | Domain models, response validation |
| `pydantic-settings` | ≥2.0 | Configuration from env vars |
| `fastapi` | ≥0.115 | REST API + MCP server |
| `uvicorn` | ≥0.30 | ASGI server |
| `httpx` | ≥0.27 | Async HTTP client (OpenMetadata API, LLM) |
| `asyncpg` | ≥0.30 | Async PostgreSQL driver |
| `fastmcp` | ≥0.1 | MCP protocol server |
| `anthropic` | ≥0.40 | Claude API client (optional) |
| `openai` | ≥1.50 | OpenAI API client (optional) |
| `ruff` | ≥0.8 | Linter + formatter (dev) |
| `mypy` | ≥1.13 | Type checker (dev) |
| `pytest` | ≥8.0 | Test framework (dev) |
| `pytest-asyncio` | ≥0.24 | Async test support (dev) |
| `Faker` | ≥30.0 | Demo data generation (dev) |

---

## 10. Acceptance Criteria

The PoC is considered complete when:

1. `make demo` brings up the full stack with no manual steps beyond setting `LLM_API_KEY`.
2. OpenMetadata shows all 6 PostgreSQL tables with auto-crawled schema.
3. The enricher has generated semantic descriptions for all 42 columns.
4. PII columns (`cust_email`, `cust_phone`, `cust_dob`, `cust_fname`) are correctly tagged.
5. At least 4 natural language queries produce correct SQL and meaningful results.
6. The generated SQL uses enriched column semantics (e.g., understands `CNCL` = cancelled).
7. Write operations (INSERT, DROP, etc.) are blocked by the validator.
8. The chat UI displays: question, generated SQL, result table, and explanation.
9. The before/after demo (Superset → Chat) is completable in under 5 minutes.
10. `make test` passes with >80% coverage on business logic.
11. `make lint` passes with zero errors.

---

## 11. Evolution Path

| PoC (Now) | Tier 1 Add-On | Tier 2 Standalone | Tier 3 Managed |
|---|---|---|---|
| PostgreSQL only | Client's real data source | Multiple sources unified | Continuous re-crawl |
| LLM-based PII detection | + Presidio for systematic scanning | + OpenLineage for full lineage | Drift detection + alerting |
| Single LLM call for SQL | + Few-shot examples from catalog | + Multi-step agent (clarify → query → explain) | Prompt lifecycle management |
| HTML chat UI | Slack/Teams integration | Grafana plugin or embedded copilot | Conversation analytics |
| No auth | OpenMetadata RBAC | Column-level access control in queries | Audit trail + compliance reports |
| Demo data | 1 real data source | Full data estate cataloged | Schema change management |
