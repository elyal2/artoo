from __future__ import annotations

import re


class SQLValidationError(Exception):
    pass


def validate_sql(sql: str) -> str:
    sql_upper = sql.upper().strip()
    forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
    ]
    for keyword in forbidden:
        if re.search(rf"\b{keyword}\b", sql_upper):
            raise SQLValidationError(f"Write operation not allowed: {keyword}")
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        raise SQLValidationError("Only SELECT/CTE queries are allowed")
    # Row limits are applied when results are fetched (see QueryPipeline); a LIMIT the user
    # asked for ("top 10") stays part of the query.
    return sql.rstrip().rstrip(";")


__all__ = ["validate_sql", "SQLValidationError"]
