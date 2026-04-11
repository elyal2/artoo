import pytest

from artoo.api.validator import SQLValidationError, validate_sql


def test_blocks_write_operations():
    with pytest.raises(SQLValidationError):
        validate_sql("INSERT INTO x VALUES (1)")


def test_adds_limit_when_missing():
    sql = validate_sql("select * from table_a")
    assert "LIMIT 100" in sql.upper()


def test_accepts_cte():
    sql = validate_sql("WITH t AS (SELECT 1) SELECT * FROM t")
    assert sql.strip().upper().startswith("WITH")
