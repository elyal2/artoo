import pytest

from artoo.api.validator import SQLValidationError, validate_sql


def test_blocks_write_operations():
    with pytest.raises(SQLValidationError):
        validate_sql("INSERT INTO x VALUES (1)")


def test_does_not_force_a_limit():
    sql = validate_sql("select * from table_a")
    assert "LIMIT" not in sql.upper()


def test_keeps_limit_the_user_asked_for():
    assert validate_sql("SELECT * FROM t ORDER BY a LIMIT 10").endswith("LIMIT 10")


def test_strips_trailing_semicolon():
    assert validate_sql("SELECT 1;  ") == "SELECT 1"


def test_accepts_cte():
    sql = validate_sql("WITH t AS (SELECT 1) SELECT * FROM t")
    assert sql.strip().upper().startswith("WITH")
