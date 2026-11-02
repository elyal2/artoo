import pytest
from fastapi.testclient import TestClient

from artoo.api import server
from artoo.api.pipeline import QueryPipeline
from artoo.api.results import (
    ResultCache,
    SortError,
    csv_chunks,
    page_of,
    parse_sort,
    sorted_rows,
)

ROWS = [
    {"id": 1, "name": "b", "amount": 5.0},
    {"id": 2, "name": "a", "amount": None},
    {"id": 3, "name": "c", "amount": 9.5},
    {"id": 4, "name": None, "amount": 1.0},
]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _put(cache: ResultCache, rows=ROWS):  # noqa: ANN001, ANN202
    return cache.put(
        question="q", sql="SELECT 1", rows=list(rows), truncated=False, column_labels={}
    )


def test_cache_returns_what_was_stored():
    cache = ResultCache(ttl_seconds=60, max_entries=5)
    stored = _put(cache)
    assert cache.get(stored.result_id) is stored
    assert stored.columns == ["id", "name", "amount"]


def test_cache_entry_expires_after_ttl_and_slides_on_access():
    clock = Clock()
    cache = ResultCache(ttl_seconds=60, max_entries=5, clock=clock)
    stored = _put(cache)
    clock.now = 50
    assert cache.get(stored.result_id) is not None  # touch: expiry moves to 110
    clock.now = 100
    assert cache.get(stored.result_id) is not None
    clock.now = 200
    assert cache.get(stored.result_id) is None


def test_cache_evicts_least_recently_used():
    cache = ResultCache(ttl_seconds=60, max_entries=2)
    a, b = _put(cache), _put(cache)
    cache.get(a.result_id)  # b is now the oldest
    c = _put(cache)
    assert cache.get(b.result_id) is None
    assert cache.get(a.result_id) is not None and cache.get(c.result_id) is not None


def test_cache_unknown_id():
    assert ResultCache(ttl_seconds=60, max_entries=2).get("nope") is None


def test_parse_sort_variants():
    cols = ["id", "name"]
    assert parse_sort(None, cols) is None
    assert parse_sort("name", cols) == ("name", False)
    assert parse_sort("name,desc", cols) == ("name", True)
    assert parse_sort("name, ASC", cols) == ("name", False)


def test_parse_sort_rejects_unknown_column_and_direction():
    with pytest.raises(SortError):
        parse_sort("nope", ["id"])
    with pytest.raises(SortError):
        parse_sort("id,sideways", ["id"])


def test_sorted_rows_puts_nulls_last_in_both_directions():
    asc = [r["amount"] for r in sorted_rows(ROWS, ("amount", False))]
    desc = [r["amount"] for r in sorted_rows(ROWS, ("amount", True))]
    assert asc == [1.0, 5.0, 9.5, None]
    assert desc == [9.5, 5.0, 1.0, None]


def test_sorted_rows_handles_mixed_types_without_crashing():
    rows = [{"v": "x"}, {"v": 3}, {"v": 1.5}]
    assert [r["v"] for r in sorted_rows(rows, ("v", False))] == [1.5, 3, "x"]


def test_page_of_slices_and_runs_off_the_end():
    rows = [{"i": i} for i in range(7)]
    assert [r["i"] for r in page_of(rows, 1, 3)] == [3, 4, 5]
    assert [r["i"] for r in page_of(rows, 2, 3)] == [6]
    assert page_of(rows, 5, 3) == []


def test_csv_has_bom_header_delimiter_and_empty_nulls():
    text = "".join(csv_chunks(ROWS, ["id", "name", "amount"], ";"))
    assert text.startswith("﻿")
    lines = text.lstrip("﻿").splitlines()
    assert lines[0] == "id;name;amount"
    assert lines[2] == "2;a;"


def test_csv_quotes_delimiters_inside_values():
    text = "".join(csv_chunks([{"a": "x,y", "b": 'say "hi"'}], ["a", "b"], ","))
    assert '"x,y"' in text and '"say ""hi"""' in text


def test_csv_streams_in_chunks():
    rows = [{"i": i} for i in range(25)]
    chunks = list(csv_chunks(rows, ["i"], ",", chunk_rows=10))
    assert len(chunks) == 4  # BOM, 10, 10, remainder
    assert "".join(chunks).count("\n") == 26


# --- HTTP endpoints -------------------------------------------------------------


@pytest.fixture
def client():  # noqa: ANN201
    pipeline = QueryPipeline.__new__(QueryPipeline)
    pipeline.results = ResultCache(ttl_seconds=60, max_entries=5)
    server.app.dependency_overrides[server.get_pipeline] = lambda: pipeline
    stored = pipeline.results.put(
        question="q",
        sql="SELECT 1",
        rows=[{"id": i, "name": f"n{i}"} for i in range(10)],
        truncated=False,
        column_labels={"id": "ID"},
    )
    yield TestClient(server.app), stored.result_id
    server.app.dependency_overrides.clear()


def test_result_page_endpoint(client):  # noqa: ANN001
    http, rid = client
    body = http.get(f"/api/results/{rid}", params={"page": 1, "size": 4}).json()
    assert body["total_rows"] == 10 and body["page"] == 1
    assert [r["id"] for r in body["rows"]] == [4, 5, 6, 7]
    assert body["column_labels"] == {"id": "ID"}


def test_result_page_sorts_before_paging(client):  # noqa: ANN001
    http, rid = client
    body = http.get(f"/api/results/{rid}", params={"size": 3, "sort": "id,desc"}).json()
    assert [r["id"] for r in body["rows"]] == [9, 8, 7]


def test_result_page_errors(client):  # noqa: ANN001
    http, rid = client
    assert http.get("/api/results/missing").status_code == 404
    assert http.get(f"/api/results/{rid}", params={"sort": "nope"}).status_code == 400
    assert http.get(f"/api/results/{rid}", params={"size": 100000}).status_code == 422
    assert http.get(f"/api/results/{rid}", params={"page": -1}).status_code == 422


def test_export_endpoint_streams_csv(client):  # noqa: ANN001
    http, rid = client
    resp = http.get(f"/api/results/{rid}/export", params={"delimiter": "pipe", "sort": "id,desc"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    lines = resp.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "id|name" and lines[1] == "9|n9" and len(lines) == 11


def test_export_rejects_unknown_delimiter(client):  # noqa: ANN001
    http, rid = client
    assert http.get(f"/api/results/{rid}/export", params={"delimiter": "x"}).status_code == 400
