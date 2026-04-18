from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal

import asyncpg
import sqlglot
import sqlglot.expressions as exp

from ..catalog.openmetadata import OpenMetadataClient
from ..config import settings
from ..llm.client import LLMClient
from ..llm.prompts import CHART_SYSTEM_PROMPT, EXPLANATION_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT, QUERY_SYSTEM_PROMPT
from ..models import (
    ChartSpec,
    ConversationMessage,
    IntentResponse,
    QueryResponse,
    SchemaColumn,
    SQLResponse,
    TableDetail,
)
from .validator import validate_sql

logger = logging.getLogger(__name__)


def _serialize_row(row: dict) -> dict:
    """Convert non-JSON-serializable types from asyncpg results."""
    result = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, (datetime, date)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _strip_markdown(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _extract_sql_response(raw: str) -> SQLResponse:
    """Parse LLM output into SQLResponse with fallbacks for malformed responses."""
    clean = _strip_markdown(raw)
    # Happy path: well-formed JSON object
    try:
        return SQLResponse.model_validate_json(clean)
    except Exception:
        pass
    # The LLM may output prose + JSON; find the last {...} block
    brace_match = re.search(r"\{[\s\S]*\}", clean)
    if brace_match:
        try:
            return SQLResponse.model_validate_json(brace_match.group(0))
        except Exception:
            pass
    # Last resort: treat the whole response as raw SQL if it looks like one
    sql_match = re.search(r"((?:WITH|SELECT)\s[\s\S]+)", clean, re.IGNORECASE)
    if sql_match:
        sql_text = sql_match.group(1).strip().rstrip(";") + ";"
        logger.warning("LLM returned raw SQL instead of JSON — wrapping with low confidence")
        return SQLResponse(sql=sql_text, tables_used=[], confidence="low")
    raise ValueError(f"Cannot parse LLM SQL response: {clean[:200]}")


class QueryPipeline:
    def __init__(self, catalog: OpenMetadataClient, llm: LLMClient | None = None) -> None:
        self.catalog = catalog
        self.llm = llm or LLMClient.default()
        self._pool: asyncpg.Pool | None = None
        self._dsn = _pg_dsn(settings.postgres_dsn)

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    async def _schema_context(self, tables: list[TableDetail]) -> str:
        parts: list[str] = []
        for table in tables:
            # Use only the short table name for SQL, not the full OM qualified name
            short_name = table.name.split(".")[-1]
            lines = [f"TABLE: {short_name} — {table.description or ''}"]
            if table.business_domain:
                lines.append(f"Business domain: {table.business_domain}")
            lines.append("COLUMNS:")
            for col in table.columns:
                line = f"  - {col.name} ({col.data_type})"
                if col.business_name:
                    line += f" — {col.business_name}"
                if col.description:
                    line += f": {col.description}"
                if col.example_values:
                    line += f" [examples: {col.example_values}]"
                lines.append(line)
            if table.foreign_keys:
                lines.append("RELATIONSHIPS:")
                for fk in table.foreign_keys:
                    lines.append(f"  - {fk}")
            schema_cols = self._schema_columns(table)
            temporal_cols = [c.name for c in schema_cols if c.is_temporal]
            numeric_cols = [c.name for c in schema_cols if c.is_numeric]
            if temporal_cols:
                lines.append(f"TEMPORAL COLUMNS: {', '.join(temporal_cols)}")
            if numeric_cols:
                lines.append(f"NUMERIC COLUMNS: {', '.join(numeric_cols)}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    @staticmethod
    def _schema_columns(table: TableDetail) -> list[SchemaColumn]:
        return OpenMetadataClient.schema_columns(table)

    @staticmethod
    def _extract_table_and_column_refs(sql: str) -> set[str]:
        """Extract only real table/column references from SQL using the AST.

        Uses sqlglot to parse the SQL and walk the AST, collecting only
        ``exp.Table`` and ``exp.Column`` node names. This correctly ignores:
        - SQL keywords and built-in functions
        - CTE aliases (WITH foo AS ...)
        - Column aliases (SELECT x AS my_alias) — both the definition and any
          reference to that alias later in ORDER BY / HAVING
        - Table aliases (FROM tbl t) — short aliases like "t"
        Falls back to an empty set if parsing fails (so validation is skipped).
        """
        try:
            statements = sqlglot.parse(sql, dialect="postgres")
        except sqlglot.errors.SqlglotError:
            return set()

        refs: set[str] = set()
        for statement in statements:
            if statement is None:
                continue

            # Collect all aliases defined anywhere in the statement so we can
            # exclude them: CTE names, column aliases (AS foo), table aliases.
            defined_aliases: set[str] = set()

            # CTE names
            for cte in statement.find_all(exp.CTE):
                if cte.alias:
                    defined_aliases.add(cte.alias.lower())

            # Column aliases (exp.Alias wraps the expression being aliased)
            for alias_node in statement.find_all(exp.Alias):
                if alias_node.alias:
                    defined_aliases.add(alias_node.alias.lower())

            # Table aliases (FROM tbl AS t  or  FROM tbl t)
            for tbl in statement.find_all(exp.Table):
                if tbl.alias:
                    defined_aliases.add(tbl.alias.lower())

            for node in statement.walk():
                if isinstance(node, exp.Table):
                    name = node.name
                    if name and name.lower() not in defined_aliases:
                        refs.add(name)
                elif isinstance(node, exp.Column):
                    col_name = node.name
                    if col_name and col_name.lower() not in defined_aliases:
                        refs.add(col_name)

        return refs

    @staticmethod
    def _validate_sql_columns(sql: str, tables: list[TableDetail]) -> None:
        """Validate that all qualified column refs (alias.col) use columns that
        actually exist in the table the alias resolves to.

        Strategy:
        1. Parse the AST and build a map of table_alias → short_table_name.
        2. For every exp.Column node that has a table qualifier, check that the
           column name exists in the resolved table's column list.
        3. Unqualified column refs and refs that resolve to CTEs/subquery aliases
           are skipped (fail-open) — the DB will catch genuine errors there.
        4. If sqlglot cannot parse the SQL, skip entirely (fail-open).
        """
        # Build lookup: short table name → set of column names
        table_columns: dict[str, set[str]] = {}
        for td in tables:
            short = td.name.split(".")[-1].lower()
            table_columns[short] = {c.name.lower() for c in td.columns}

        try:
            statements = sqlglot.parse(sql, dialect="postgres")
        except sqlglot.errors.SqlglotError:
            logger.debug("_validate_sql_columns: parse failed, skipping")
            return

        for statement in statements:
            if statement is None:
                continue

            # Collect aliases that point to CTEs or subqueries — not real tables
            virtual_aliases: set[str] = set()
            for cte in statement.find_all(exp.CTE):
                if cte.alias:
                    virtual_aliases.add(cte.alias.lower())
            for subq in statement.find_all(exp.Subquery):
                if subq.alias:
                    virtual_aliases.add(subq.alias.lower())

            # Map table alias → resolved short name (only real tables, not CTEs)
            alias_to_table: dict[str, str] = {}
            for tbl in statement.find_all(exp.Table):
                tname = tbl.name.lower() if tbl.name else ""
                talias = tbl.alias.lower() if tbl.alias else tname
                if tname and tname not in virtual_aliases and talias not in virtual_aliases:
                    alias_to_table[talias] = tname
                    alias_to_table[tname] = tname  # also allow unaliased refs

            # Collect column aliases so we skip them as qualifiers
            col_aliases: set[str] = set()
            for alias_node in statement.find_all(exp.Alias):
                if alias_node.alias:
                    col_aliases.add(alias_node.alias.lower())

            # Validate each qualified column reference
            for node in statement.find_all(exp.Column):
                qualifier = node.table.lower() if node.table else None
                col_name = node.name.lower() if node.name else None
                if not qualifier or not col_name:
                    continue
                # Skip if qualifier is a CTE/subquery alias or a column alias
                if qualifier in virtual_aliases or qualifier in col_aliases:
                    continue
                resolved_table = alias_to_table.get(qualifier)
                if resolved_table is None:
                    continue  # unknown qualifier — let DB catch it
                allowed_cols = table_columns.get(resolved_table)
                if allowed_cols is None:
                    continue  # table not in our schema context — let DB catch it
                if col_name not in allowed_cols:
                    raise ValueError(
                        f"Column '{node.table}.{node.name}' does not exist: "
                        f"'{node.name}' is not a column of table '{resolved_table}'. "
                        f"Available: {', '.join(sorted(allowed_cols))}"
                    )

    async def _generate_sql_with_retry(
        self, base_user_msg: str, tables: list[TableDetail], max_retries: int = 1
    ) -> tuple[SQLResponse, str]:
        """Generate SQL, validate it, and retry once with the error as feedback."""
        user_msg = base_user_msg
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0 and last_error:
                user_msg = (
                    f"{base_user_msg}\n\n"
                    f"Your previous attempt produced invalid SQL. Error: {last_error}\n"
                    f"Fix the SQL addressing the error above. Check the schema carefully: "
                    f"every column and every join path must exist in the COLUMNS and RELATIONSHIPS sections."
                )
                logger.info("Retrying SQL generation after error (attempt %d): %s", attempt + 1, last_error)

            raw = await self.llm.complete(system=QUERY_SYSTEM_PROMPT, user=user_msg)
            parsed = _extract_sql_response(raw)
            sql = validate_sql(parsed.sql)
            logger.info(
                "Generated SQL (attempt %d)",
                attempt + 1,
                extra={"sql": sql, "tables": parsed.tables_used, "confidence": parsed.confidence},
            )

            # Pre-execution column validation
            try:
                self._validate_sql_columns(sql, tables)
            except ValueError as col_err:
                last_error = str(col_err)
                continue

            # EXPLAIN dry-run — catches type mismatches, missing refs, bad aliases
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                try:
                    await conn.execute(f"EXPLAIN {sql}", timeout=10)
                    return parsed, sql
                except Exception as exc:
                    pg_msg = str(exc).split("\n")[0]
                    hint_match = re.search(r"HINT:\s*(.+)", str(exc))
                    if hint_match:
                        pg_msg = f"{pg_msg} — {hint_match.group(1)}"
                    last_error = pg_msg

        raise ValueError(last_error or "SQL generation failed")

    async def query(
        self, question: str, history: list[ConversationMessage] | None = None
    ) -> QueryResponse:
        # ── intent classification ─────────────────────────────────────────────
        conversation_context = ""
        if history:
            for msg in history[-6:]:
                if msg.role == "user":
                    conversation_context += f"User: {msg.content}\n"
                elif msg.role == "assistant":
                    conversation_context += f"Assistant: {msg.content}\n"

        intent_raw = await self.llm.complete(
            system=INTENT_SYSTEM_PROMPT,
            user=f"Conversation history:\n{conversation_context}\nNew message: {question}",
        )
        try:
            intent = IntentResponse.model_validate_json(_strip_markdown(intent_raw))
        except Exception:
            intent = IntentResponse(intent="data_query")

        if intent.intent == "conversational":
            reply = intent.reply or "I can query your data catalog and answer questions about the data. Try asking something like 'show top revenue by hotel' or 'how many bookings last month'."
            return QueryResponse(question=question, explanation=reply, confidence="high")

        # ── data query path ───────────────────────────────────────────────────
        tables = await self.catalog.semantic_search(question, n_results=5)
        if not tables:
            summaries = await self.catalog.list_tables()
            tables = [await self.catalog.get_table(s.name) for s in summaries[:10]]
        context = await self._schema_context(tables)

        sql_context = ""
        if history:
            for msg in history[-6:]:
                if msg.role == "user":
                    sql_context += f"Previous question: {msg.content}\n"
                elif msg.role == "assistant":
                    sql_context += f"Previous SQL: {msg.content}\n"
            sql_context += "\n"

        base_user_msg = f"Conversation history:\n{sql_context}New question: {question}\nSchema:\n{context}"
        parsed, sql = await self._generate_sql_with_retry(base_user_msg, tables)

        pool = await self._ensure_pool()
        timeout = settings.query_timeout_seconds
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, timeout=timeout)
        rows_dict = [_serialize_row(dict(r)) for r in rows[: settings.max_result_rows]]

        explanation = await self.llm.complete(
            system=EXPLANATION_SYSTEM_PROMPT,
            user=json.dumps({"question": question, "sql": sql, "sample": rows_dict[:5]}),
        )

        column_labels = self._build_column_labels(tables, rows_dict)

        chart_spec = await self._recommend_chart(question, sql, rows_dict, column_labels)

        return QueryResponse(
            question=question,
            sql=sql,
            explanation=explanation,
            rows=rows_dict,
            tables_used=parsed.tables_used,
            confidence=parsed.confidence,
            column_labels=column_labels,
            chart_spec=chart_spec,
        )

    async def _recommend_chart(
        self, question: str, sql: str, rows: list[dict], column_labels: dict[str, str]
    ) -> ChartSpec | None:
        if not rows or len(rows) < 2:
            logger.debug("Chart skipped: fewer than 2 rows")
            return None
        chart_model = settings.llm_chart_model or None
        logger.info(
            "Chart LLM call starting",
            extra={"chart_model": chart_model or self.llm.model, "rows": len(rows)},
        )
        try:
            raw = await self.llm.complete(
                system=CHART_SYSTEM_PROMPT,
                user=json.dumps(
                    {
                        "question": question,
                        "sql": sql,
                        "data_sample": rows[:30],
                        "column_labels": column_labels,
                    },
                    default=str,
                ),
                model=chart_model,
                max_tokens=settings.llm_chart_max_tokens,
            )
            logger.debug("Chart LLM raw response length: %d", len(raw) if raw else 0)
            clean = _strip_markdown(raw)
            parsed = json.loads(clean)
            chart = ChartSpec.model_validate(parsed)
            logger.info(
                "Chart generated",
                extra={"chart_type": chart.chart_type, "has_d3_code": bool(chart.d3_code)},
            )
            return chart
        except Exception as exc:
            logger.warning("Chart generation failed: %s", exc, exc_info=True)
            return None

    def _build_column_labels(self, tables: list[TableDetail], rows: list[dict]) -> dict[str, str]:
        if not rows:
            return {}
        col_names = list(rows[0].keys())
        label_map: dict[str, str] = {}
        for table in tables:
            for col in table.columns:
                if col.name in col_names:
                    label_map[col.name] = col.business_name or col.description or col.name
        for col_name in col_names:
            if col_name not in label_map:
                label_map[col_name] = col_name
        return label_map

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()


def _pg_dsn(raw_dsn: str) -> str:
    dsn = raw_dsn.replace("+psycopg2", "")
    if "postgres:5432" in dsn and "postgresql:5432" not in dsn:
        dsn = dsn.replace("postgres:5432", "postgresql:5432")
    return dsn


__all__ = ["QueryPipeline"]
