from __future__ import annotations

from fastmcp import FastMCP

from ..catalog.openmetadata import OpenMetadataClient
from .pipeline import QueryPipeline


def create_mcp_server(pipeline: QueryPipeline, catalog: OpenMetadataClient) -> FastMCP:
    mcp = FastMCP("artoo")

    @mcp.tool()
    async def query_data(question: str) -> dict:
        """Ask a question about the data in natural language."""
        result = await pipeline.query(question)
        return result.model_dump()

    @mcp.tool()
    async def list_tables() -> list[dict]:
        """List tables from the semantic catalog."""
        tables = await catalog.list_tables()
        return [t.model_dump() for t in tables]

    @mcp.tool()
    async def describe_table(table_name: str) -> dict:
        """Get details for a table."""
        result = await catalog.get_table(table_name)
        return result.model_dump()

    return mcp


__all__ = ["create_mcp_server"]
