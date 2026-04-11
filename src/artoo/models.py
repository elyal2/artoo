from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    name: str
    data_type: str
    description: Optional[str] = None
    business_name: Optional[str] = None
    foreign_key: Optional[str] = None
    example_values: Optional[str] = None


class TableContext(BaseModel):
    name: str
    columns: List[ColumnMeta]
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)
    foreign_keys: List[str] = Field(default_factory=list)
    column_stats: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    row_count: int = 0


class ColumnEnrichment(BaseModel):
    description: str
    business_name: str
    pii: bool
    pii_type: Optional[str] = None
    sensitivity: str = "internal"
    example_values: Optional[str] = None


class TableEnrichment(BaseModel):
    table_description: str
    business_domain: Optional[str] = None
    columns: Dict[str, ColumnEnrichment]
    suggested_tags: List[str] = Field(default_factory=list)
    common_queries: List[str] = Field(default_factory=list)


class SQLResponse(BaseModel):
    sql: str
    tables_used: List[str]
    confidence: Literal["high", "medium", "low"] = "medium"
    reasoning: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    sql: str
    explanation: str
    rows: List[Dict[str, Any]]
    tables_used: List[str]
    confidence: str


class TableSummary(BaseModel):
    name: str
    description: Optional[str] = None
    business_domain: Optional[str] = None


class TableDetail(BaseModel):
    name: str
    description: Optional[str] = None
    business_domain: Optional[str] = None
    columns: List[ColumnMeta]
    foreign_keys: List[str] = Field(default_factory=list)


__all__ = [
    "ColumnMeta",
    "TableContext",
    "ColumnEnrichment",
    "TableEnrichment",
    "SQLResponse",
    "QueryResponse",
    "TableSummary",
    "TableDetail",
]
