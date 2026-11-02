"""Data model of a catalog proposal: what the documentation suggests, before/after, and why."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from ..models import TableDetail

ItemField = Literal[
    "table_description",
    "table_business_rules",
    "table_display_name",
    "column_description",
    "column_display_name",
]
Confidence = Literal["high", "medium", "low"]

COLUMN_FIELDS: frozenset[str] = frozenset({"column_description", "column_display_name"})


def item_id(table: str, column: str | None, field: str) -> str:
    raw = f"{table}|{column or ''}|{field}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]  # noqa: S324 - stable id, not security


class ProposalItem(BaseModel):
    id: str
    table: str  # fully qualified OpenMetadata name
    column: str | None = None
    field: ItemField
    before: str | None = None
    after: str
    source: str
    confidence: Confidence = "medium"
    rationale: str = ""


class OpenQuestion(BaseModel):
    question: str
    source: str = ""
    tables: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    summary: str = ""
    documents: list[str] = Field(default_factory=list)
    items: list[ProposalItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    items: list[ProposalItem]


class ApplyOutcome(BaseModel):
    id: str
    status: Literal["ok", "error"]
    detail: str = ""


class ApplyResult(BaseModel):
    outcomes: list[ApplyOutcome]

    @property
    def applied(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "ok")


def current_value(table: TableDetail, column: str | None, field: str) -> str | None:
    """What the catalog holds today for the thing an item would change."""
    if field == "table_description":
        return table.description
    if field == "table_business_rules":
        return table.business_rules
    if field == "table_display_name":
        return table.display_name
    col = next((c for c in table.columns if c.name == column), None)
    if col is None:
        return None
    return col.description if field == "column_description" else col.business_name
