from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from ..catalog.openmetadata import OpenMetadataClient, get_default_client
from ..logging import configure_logging
from ..models import ConversationMessage, QueryResponse, TableDetail, TableSummary
from .pipeline import QueryPipeline

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    history: list[ConversationMessage] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api") and not request.url.path.startswith("/mcp"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheStaticMiddleware)


async def get_pipeline() -> QueryPipeline:
    pipeline: QueryPipeline = app.state.pipeline
    return pipeline


async def get_catalog() -> OpenMetadataClient:
    catalog: OpenMetadataClient = app.state.catalog
    return catalog


@app.post("/api/query", response_model=QueryResponse)
async def api_query(
    req: QueryRequest, pipeline: QueryPipeline = Depends(get_pipeline)
) -> QueryResponse:
    try:
        return await pipeline.query(req.question, req.history)
    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(exc))


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
    return app.state.pipeline


def _get_catalog_from_state() -> OpenMetadataClient:
    return app.state.catalog


def create_mcp_app():
    from fastmcp import FastMCP

    mcp = FastMCP("artoo")

    @mcp.tool()
    async def query_data(question: str) -> dict:
        """Ask a question about the data in natural language."""
        pipeline = _get_pipeline_from_state()
        result = await pipeline.query(question)
        return result.model_dump()

    @mcp.tool()
    async def list_tables() -> list[dict]:
        """List tables from the semantic catalog."""
        catalog = _get_catalog_from_state()
        tables = await catalog.list_tables()
        return [t.model_dump() for t in tables]

    @mcp.tool()
    async def describe_table(table_name: str) -> dict:
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
