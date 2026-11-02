from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ..catalog.openmetadata import OpenMetadataClient, get_default_client
from ..config import settings
from ..enricher.applier import ProposalApplier
from ..enricher.doc_enricher import DocEnricher
from ..enricher.documents import UploadedFile
from ..enricher.proposal import ApplyRequest, ApplyResult, Proposal
from ..logging import configure_logging
from ..models import (
    ConversationMessage,
    QueryResponse,
    ResultPage,
    TableDetail,
    TableSummary,
)
from .pipeline import QueryPipeline
from .results import (
    DELIMITERS,
    SortError,
    StoredResult,
    csv_chunks,
    page_of,
    parse_sort,
    sorted_rows,
)

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    history: list[ConversationMessage] = []
    page_size: int | None = Field(default=None, ge=1, le=settings.result_page_size_max)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    catalog = await get_default_client()
    pipeline = QueryPipeline(catalog)

    app.state.catalog = catalog
    app.state.pipeline = pipeline
    yield
    await pipeline.close()
    await catalog.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Add no-cache headers to all static file responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api") and not request.url.path.startswith("/mcp"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheStaticMiddleware)


async def get_pipeline() -> QueryPipeline:
    return cast(QueryPipeline, app.state.pipeline)


async def get_catalog() -> OpenMetadataClient:
    return cast(OpenMetadataClient, app.state.catalog)


@app.post("/api/query", response_model=QueryResponse)
async def api_query(
    req: QueryRequest, pipeline: QueryPipeline = Depends(get_pipeline)
) -> QueryResponse:
    try:
        return await pipeline.query(req.question, req.history, req.page_size)
    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(exc))


def _stored_result(pipeline: QueryPipeline, result_id: str) -> StoredResult:
    stored = pipeline.results.get(result_id)
    if stored is None:
        raise HTTPException(
            status_code=404, detail="Result expired or not found; ask the question again."
        )
    return stored


def _sorted(stored: StoredResult, sort: str | None) -> list[dict[str, Any]]:
    try:
        return sorted_rows(stored.rows, parse_sort(sort, stored.columns))
    except SortError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _result_page(stored: StoredResult, page: int, size: int, sort: str | None) -> ResultPage:
    rows = _sorted(stored, sort)
    return ResultPage(
        result_id=stored.result_id,
        page=page,
        page_size=size,
        total_rows=len(rows),
        truncated=stored.truncated,
        sort=sort,
        columns=stored.columns,
        column_labels=stored.column_labels,
        rows=page_of(rows, page, size),
    )


@app.get("/api/results/{result_id}", response_model=ResultPage)
async def api_result_page(
    result_id: str,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=settings.result_page_size, ge=1, le=settings.result_page_size_max),
    sort: str | None = Query(default=None, description="column or column,asc|desc"),
    pipeline: QueryPipeline = Depends(get_pipeline),
) -> ResultPage:
    return _result_page(_stored_result(pipeline, result_id), page, size, sort)


@app.get("/api/results/{result_id}/export")
async def api_result_export(
    result_id: str,
    delimiter: str = Query(default="comma", description="comma | semicolon | pipe | tab"),
    sort: str | None = Query(default=None, description="column or column,asc|desc"),
    pipeline: QueryPipeline = Depends(get_pipeline),
) -> StreamingResponse:
    if delimiter not in DELIMITERS:
        raise HTTPException(
            status_code=400, detail=f"delimiter must be one of: {', '.join(DELIMITERS)}"
        )
    stored = _stored_result(pipeline, result_id)
    rows = _sorted(stored, sort)
    return StreamingResponse(
        csv_chunks(rows, stored.columns, DELIMITERS[delimiter]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="artoo-{stored.result_id}.csv"'},
    )


MAX_UPLOAD_FILES = 10


@app.post("/api/catalog/propose", response_model=Proposal)
async def api_catalog_propose(
    files: list[UploadFile] = File(...),
    instructions: str = Form(default=""),
    catalog: OpenMetadataClient = Depends(get_catalog),
) -> Proposal:
    """Read business documentation and propose catalog changes. Writes nothing."""
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_UPLOAD_FILES} files per upload.")
    uploads = [UploadedFile(f.filename or "document", await f.read()) for f in files]
    try:
        return await DocEnricher(catalog).propose(uploads, instructions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Documentation enrichment failed")
        raise HTTPException(
            status_code=502, detail=f"The model could not process the documents: {exc}"
        )


@app.post("/api/catalog/apply", response_model=ApplyResult)
async def api_catalog_apply(
    req: ApplyRequest, catalog: OpenMetadataClient = Depends(get_catalog)
) -> ApplyResult:
    """Write the reviewed (and possibly edited) items of a proposal to OpenMetadata."""
    if not req.items:
        raise HTTPException(status_code=400, detail="No items to apply.")
    return await ProposalApplier(catalog).apply(req.items)


@app.get("/api/tables", response_model=list[TableSummary])
async def api_tables(catalog: OpenMetadataClient = Depends(get_catalog)) -> list[TableSummary]:
    return await catalog.list_tables()


@app.get("/api/table/{table_name}", response_model=TableDetail)
async def api_table(
    table_name: str, catalog: OpenMetadataClient = Depends(get_catalog)
) -> TableDetail:
    return await catalog.get_table(table_name)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _get_pipeline_from_state() -> QueryPipeline:
    return cast(QueryPipeline, app.state.pipeline)


def _get_catalog_from_state() -> OpenMetadataClient:
    return cast(OpenMetadataClient, app.state.catalog)


def create_mcp_app() -> Any:
    from fastmcp import FastMCP

    mcp = FastMCP("artoo")

    @mcp.tool()
    async def query_data(question: str) -> dict[str, Any]:
        """Ask a question about the data in natural language."""
        pipeline = _get_pipeline_from_state()
        result = await pipeline.query(question)
        return result.model_dump()

    @mcp.tool()
    async def get_result_page(
        result_id: str,
        page: int = 0,
        size: int = settings.result_page_size,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Read another page of a previous query_data result (use its result_id)."""
        size = max(1, min(size, settings.result_page_size_max))
        try:
            stored = _stored_result(_get_pipeline_from_state(), result_id)
            return _result_page(stored, max(page, 0), size, sort).model_dump()
        except HTTPException as exc:
            raise ValueError(exc.detail) from exc

    @mcp.tool()
    async def list_tables() -> list[dict[str, Any]]:
        """List tables from the semantic catalog."""
        catalog = _get_catalog_from_state()
        tables = await catalog.list_tables()
        return [t.model_dump() for t in tables]

    @mcp.tool()
    async def describe_table(table_name: str) -> dict[str, Any]:
        """Get details for a table."""
        catalog = _get_catalog_from_state()
        result = await catalog.get_table(table_name)
        return result.model_dump()

    return mcp.http_app()


mcp_asgi = create_mcp_app()
app.mount("/mcp", mcp_asgi)


static_dir = Path(__file__).resolve().parent.parent / "chat"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
