"""Propose catalog improvements from business documentation, grounded in what OpenMetadata
already knows. Nothing is written here: the proposal is reviewed first (see applier.py)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from ..catalog.openmetadata import OpenMetadataClient
from ..config import settings
from ..llm.client import LLMClient
from ..llm.prompts import DOC_ENRICHMENT_SYSTEM_PROMPT
from ..models import TableDetail
from .documents import LoadedDocuments, UploadedFile, load_documents
from .proposal import (
    COLUMN_FIELDS,
    OpenQuestion,
    Proposal,
    ProposalItem,
    current_value,
    item_id,
)

logger = logging.getLogger(__name__)

_MAX_COLUMN_TEXT = 400
_SCHEMA_NOISE = ("information_schema", "pg_catalog")


def _short(fqn: str) -> str:
    return fqn.split(".")[-1]


def format_catalog(tables: list[TableDetail]) -> str:
    """The catalog as the model sees it: the domain is whatever OpenMetadata holds."""
    parts: list[str] = []
    for t in tables:
        lines = [f"TABLE {_short(t.name)}"]
        if t.display_name:
            lines.append(f"  display name: {t.display_name}")
        if t.business_domain:
            lines.append(f"  domain: {t.business_domain}")
        lines.append(f"  description: {t.description or '(none)'}")
        lines.append(f"  business rules: {t.business_rules or '(none)'}")
        lines.append("  columns:")
        for c in t.columns:
            desc = (c.description or "").replace("\n", " ")[:_MAX_COLUMN_TEXT]
            label = f" [{c.business_name}]" if c.business_name else ""
            lines.append(f"    - {c.name} ({c.data_type}){label}: {desc or '(none)'}")
        if t.foreign_keys:
            lines.append("  foreign keys:")
            lines.extend(f"    - {fk}" for fk in t.foreign_keys)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+)", text)
    return match.group(1).strip() if match else text


def _objects_of(text: str, key: str) -> list[dict[str, Any]]:
    """Complete objects of the array `"key": [...]`, tolerating a truncated tail."""
    match = re.search(rf'"{key}"\s*:\s*\[', text)
    if not match:
        return []
    decoder = json.JSONDecoder()
    pos, found = match.end(), []
    while True:
        while pos < len(text) and text[pos] in " \n\r\t,":
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            break
        try:
            obj, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break  # truncated object: keep the complete ones before it
        if isinstance(obj, dict):
            found.append(obj)
    return found


def parse_model_output(raw: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    """(summary, items, open_questions, was_truncated)."""
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return (
                str(data.get("summary") or ""),
                [i for i in data.get("items") or [] if isinstance(i, dict)],
                [q for q in data.get("open_questions") or [] if isinstance(q, dict)],
                False,
            )
    except json.JSONDecodeError:
        pass
    summary = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    return (
        json.loads(f'"{summary.group(1)}"') if summary else "",
        _objects_of(text, "items"),
        _objects_of(text, "open_questions"),
        True,
    )


class DocEnricher:
    def __init__(self, catalog: OpenMetadataClient, llm: LLMClient | None = None) -> None:
        self.catalog = catalog
        self.llm = llm or LLMClient.default()

    async def _load_catalog(self) -> list[TableDetail]:
        summaries = await self.catalog.list_tables()
        tables = [s for s in summaries if not any(n in s.name for n in _SCHEMA_NOISE)]
        return [await self.catalog.get_table(s.name) for s in tables]

    async def propose(self, files: list[UploadedFile], instructions: str = "") -> Proposal:
        docs = load_documents(
            files,
            max_total_bytes=settings.doc_max_upload_mb * 1_048_576,
            max_text_chars=settings.doc_max_text_chars,
        )
        if not docs.attachments and not docs.texts:
            return Proposal(summary="No readable documents were provided.", warnings=docs.warnings)
        tables = await self._load_catalog()
        if not tables:
            raise ValueError("The catalog has no tables yet: run the ingestion first.")

        raw = await self._ask_model(tables, docs, instructions)
        summary, items, questions, truncated = parse_model_output(raw)

        proposal = Proposal(summary=summary, documents=docs.names, warnings=list(docs.warnings))
        if truncated:
            proposal.warnings.append(
                "The model's answer was cut off; only the complete items are shown. "
                "Upload fewer documents or run it again for the rest."
            )
        self._add_items(proposal, tables, items)
        self._add_questions(proposal, tables, questions)
        return proposal

    async def _ask_model(
        self, tables: list[TableDetail], docs: LoadedDocuments, instructions: str
    ) -> str:
        parts = [f"CURRENT CATALOG\n\n{format_catalog(tables)}"]
        if docs.texts:
            parts.append(f"DOCUMENTS (text)\n\n{docs.prompt_text()}")
        if docs.attachments:
            names = ", ".join(a.name for a in docs.attachments)
            parts.append(f"The attached files, in order, are: {names}.")
        if instructions.strip():
            parts.append(
                f"REVIEWER'S NOTE (context from the person uploading)\n{instructions.strip()}"
            )
        parts.append("Return the JSON now.")
        model = settings.doc_enricher_model or settings.enrichment_llm_model or None
        return await self.llm.complete(
            system=DOC_ENRICHMENT_SYSTEM_PROMPT,
            user="\n\n".join(parts),
            model=model,
            max_tokens=settings.doc_enricher_max_tokens,
            attachments=docs.attachments or None,
        )

    @staticmethod
    def _resolve_table(tables: list[TableDetail], name: str) -> TableDetail | None:
        wanted = name.strip().lower()
        for t in tables:
            if t.name.lower() == wanted or _short(t.name).lower() == wanted:
                return t
        return None

    def _add_items(
        self, proposal: Proposal, tables: list[TableDetail], raw_items: list[dict[str, Any]]
    ) -> None:
        seen: dict[str, ProposalItem] = {}
        dropped = unchanged = 0
        for raw in raw_items:
            table = self._resolve_table(tables, str(raw.get("table") or ""))
            field = raw.get("field")
            column = raw.get("column") or None
            after = str(raw.get("after") or "").strip()
            source = str(raw.get("source") or "").strip()
            if table is None or not after or not source:
                dropped += 1
                continue
            if field in COLUMN_FIELDS:
                if column is None or column not in {c.name for c in table.columns}:
                    dropped += 1
                    continue
            else:
                column = None
            before = current_value(table, column, str(field))
            if before is not None and before.strip() == after:
                unchanged += 1
                continue
            try:
                item = ProposalItem(
                    id=item_id(table.name, column, str(field)),
                    table=table.name,
                    column=column,
                    field=field,  # type: ignore[arg-type]
                    before=before,
                    after=after,
                    source=source,
                    confidence=str(raw.get("confidence") or "medium"),  # type: ignore[arg-type]
                    rationale=str(raw.get("rationale") or ""),
                )
            except ValidationError:
                dropped += 1
                continue
            seen[item.id] = item
        proposal.items = list(seen.values())
        if dropped:
            proposal.warnings.append(
                f"{dropped} suggestion(s) discarded: unknown table/column, or missing source/value."
            )
        if unchanged:
            logger.info("Discarded %d suggestions identical to the current catalog", unchanged)

    def _add_questions(
        self, proposal: Proposal, tables: list[TableDetail], raw_questions: list[dict[str, Any]]
    ) -> None:
        for raw in raw_questions:
            question = str(raw.get("question") or "").strip()
            if not question:
                continue
            names = []
            for n in raw.get("tables") or []:
                table = self._resolve_table(tables, str(n))
                if table is not None:
                    names.append(_short(table.name))
            proposal.open_questions.append(
                OpenQuestion(question=question, source=str(raw.get("source") or ""), tables=names)
            )
