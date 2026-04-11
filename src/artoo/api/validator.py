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
    if "LIMIT" not in sql_upper:
        sql = f"{sql.rstrip(';')} LIMIT 100"
    return sql


__all__ = ["validate_sql", "SQLValidationError"]
