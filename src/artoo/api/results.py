"""In-memory store of query results so a question runs once and is paged/exported from memory."""

from __future__ import annotations

import csv
import io
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

DELIMITERS: dict[str, str] = {"comma": ",", "semicolon": ";", "pipe": "|", "tab": "\t"}


class SortError(ValueError):
    pass


@dataclass(slots=True)
class StoredResult:
    result_id: str
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool
    column_labels: dict[str, str]
    expires_at: float


class ResultCache:
    """LRU + sliding-TTL cache. Entries are bounded in count; each holds at most the row cap."""

    def __init__(
        self,
        ttl_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._items: OrderedDict[str, StoredResult] = OrderedDict()

    def put(
        self,
        *,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
        truncated: bool,
        column_labels: dict[str, str],
    ) -> StoredResult:
        self._purge()
        result = StoredResult(
            result_id=secrets.token_urlsafe(12),
            question=question,
            sql=sql,
            columns=list(rows[0].keys()) if rows else [],
            rows=rows,
            truncated=truncated,
            column_labels=column_labels,
            expires_at=self._clock() + self._ttl,
        )
        self._items[result.result_id] = result
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return result

    def get(self, result_id: str) -> StoredResult | None:
        self._purge()
        result = self._items.get(result_id)
        if result is None:
            return None
        result.expires_at = self._clock() + self._ttl
        self._items.move_to_end(result_id)
        return result

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, v in self._items.items() if v.expires_at <= now]:
            del self._items[key]


def parse_sort(sort: str | None, columns: list[str]) -> tuple[str, bool] | None:
    """`column` or `column,asc|desc` -> (column, descending). None when no sort requested."""
    if not sort:
        return None
    name, _, direction = sort.partition(",")
    name, direction = name.strip(), direction.strip().lower()
    if name not in columns:
        raise SortError(f"Unknown sort column '{name}'. Available: {', '.join(columns)}")
    if direction not in ("", "asc", "desc"):
        raise SortError("Sort direction must be 'asc' or 'desc'")
    return name, direction == "desc"


def _sort_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, bool):
        return (1, str(value))
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, str(value))


def sorted_rows(rows: list[dict[str, Any]], sort: tuple[str, bool] | None) -> list[dict[str, Any]]:
    """Stable sort; NULLs always last."""
    if sort is None:
        return rows
    column, descending = sort
    present = [r for r in rows if r.get(column) is not None]
    missing = [r for r in rows if r.get(column) is None]
    present.sort(key=lambda r: _sort_key(r[column]), reverse=descending)
    return present + missing


def page_of(rows: list[dict[str, Any]], page: int, size: int) -> list[dict[str, Any]]:
    return rows[page * size : (page + 1) * size]


def csv_chunks(
    rows: list[dict[str, Any]], columns: list[str], delimiter: str, chunk_rows: int = 1000
) -> Iterator[str]:
    """CSV text in chunks, UTF-8 BOM first so spreadsheets open accents correctly."""
    yield "﻿"
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    for i, row in enumerate(rows, 1):
        writer.writerow([_cell(row.get(c)) for c in columns])
        if i % chunk_rows == 0:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return str(value)
    return value
