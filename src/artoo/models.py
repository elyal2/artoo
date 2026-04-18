from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


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
    example_values: Optional[Union[str, List[Any]]] = None

    @field_validator("example_values", mode="before")
    @classmethod
    def coerce_example_values(cls, v: Any) -> Optional[str]:
        if isinstance(v, list):
            return ", ".join(str(i) for i in v)
        return v if isinstance(v, str) else None


class TableEnrichment(BaseModel):
    table_description: str
    business_domain: Optional[str] = None
    tier: int = Field(default=3, ge=1, le=5)
    columns: Dict[str, ColumnEnrichment]
    suggested_tags: List[str] = Field(default_factory=list)
    common_queries: List[str] = Field(default_factory=list)


class IntentResponse(BaseModel):
    intent: Literal["data_query", "conversational"]
    reply: Optional[str] = None


class SQLResponse(BaseModel):
    sql: str
    tables_used: List[str]
    confidence: Literal["high", "medium", "low"] = "medium"
    reasoning: Optional[str] = None


class ChartSpec(BaseModel):
    chart_type: Literal[
        "line",
        "area",
        "stacked_area",
        "bar",
        "horizontal_bar",
        "grouped_bar",
        "stacked_bar",
        "scatter",
        "bubble",
        "histogram",
        "boxplot",
        "heatmap",
        "calendar_heatmap",
        "treemap",
        "pie",
        "donut",
        "table",
        "none",
    ]
    analysis: Optional[str] = None
    d3_code: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    explanation: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    tables_used: List[str] = Field(default_factory=list)
    confidence: str = "high"
    column_labels: Dict[str, str] = Field(default_factory=dict)
    chart_spec: Optional[ChartSpec] = None


class TableSummary(BaseModel):
    name: str
    description: Optional[str] = None
    business_domain: Optional[str] = None


class TableDetail(BaseModel):
    name: str
    description: Optional[str] = None
    display_name: Optional[str] = None
    business_domain: Optional[str] = None
    columns: List[ColumnMeta]
    foreign_keys: List[str] = Field(default_factory=list)


class SchemaColumn(BaseModel):
    name: str
    data_type: str
    is_temporal: bool = False
    is_numeric: bool = False


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Optional[str] = None


__all__ = [
    "ColumnMeta",
    "TableContext",
    "ColumnEnrichment",
    "TableEnrichment",
    "SQLResponse",
    "QueryResponse",
    "ChartSpec",
    "TableSummary",
    "TableDetail",
    "ConversationMessage",
]
