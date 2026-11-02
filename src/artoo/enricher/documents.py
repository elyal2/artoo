"""Turn uploaded files into what a multimodal model can read (PDF/image blocks or plain text)."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field

from ..llm.client import Attachment

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
TEXT_SUFFIXES = {
    ".csv", ".tsv", ".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".sql", ".html", ".htm",
}  # fmt: skip
TEXT_ENCODINGS = ("utf-8", "cp1252", "latin-1")  # client exports are often cp1252


@dataclass(frozen=True, slots=True)
class UploadedFile:
    name: str
    data: bytes


@dataclass(slots=True)
class LoadedDocuments:
    attachments: list[Attachment] = field(default_factory=list)
    texts: list[tuple[str, str]] = field(default_factory=list)  # (name, text)
    names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def prompt_text(self) -> str:
        """Text documents, fenced so the model sees where each one starts and ends."""
        return "\n\n".join(f'<document name="{n}">\n{t}\n</document>' for n, t in self.texts)


def _suffix(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot >= 0 else ""


def _decode(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    )


def load_documents(
    files: list[UploadedFile], *, max_total_bytes: int, max_text_chars: int
) -> LoadedDocuments:
    loaded = LoadedDocuments()
    total = sum(len(f.data) for f in files)
    if total > max_total_bytes:
        raise ValueError(
            f"Uploads total {total / 1_048_576:.1f} MB; the limit is "
            f"{max_total_bytes / 1_048_576:.0f} MB."
        )
    for f in files:
        suffix = _suffix(f.name)
        if not f.data:
            loaded.warnings.append(f"{f.name}: empty file, skipped")
            continue
        if suffix == ".pdf":
            loaded.attachments.append(
                Attachment("application/pdf", base64.b64encode(f.data).decode(), f.name)
            )
        elif suffix in IMAGE_TYPES:
            loaded.attachments.append(
                Attachment(IMAGE_TYPES[suffix], base64.b64encode(f.data).decode(), f.name)
            )
        elif suffix == ".docx":
            try:
                loaded.texts.append((f.name, _docx_text(f.data)[:max_text_chars]))
            except (zipfile.BadZipFile, KeyError):
                loaded.warnings.append(f"{f.name}: not a readable .docx, skipped")
                continue
        elif suffix in TEXT_SUFFIXES:
            text = _decode(f.data)
            if len(text) > max_text_chars:
                loaded.warnings.append(
                    f"{f.name}: truncated to the first {max_text_chars:,} characters"
                )
            loaded.texts.append((f.name, text[:max_text_chars]))
        else:
            loaded.warnings.append(
                f"{f.name}: unsupported type '{suffix or 'none'}' (use PDF, image, docx, csv, md, txt, json, yaml, sql)"
            )
            continue
        loaded.names.append(f.name)
    return loaded
