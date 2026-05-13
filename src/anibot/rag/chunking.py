from __future__ import annotations

from dataclasses import dataclass
import re

from anibot.rag.manifest import DocumentSpec
from anibot.rag.pdf_extract import PageText


TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
HEADING_RE = re.compile(r"^(\d+(\.\d+)*\s+.+|[A-Z][A-Z0-9 /,\-()]{8,})$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    page_number: int
    sequence: int
    title: str
    heading: str
    text: str
    crop: str
    document_type: str
    advisory_tier: str
    allowed_use: str
    reviewed: bool
    source_agency: str
    year: int
    source_filename: str


def chunk_document(
    spec: DocumentSpec,
    pages: list[PageText],
    target_tokens: int = 700,
    overlap_tokens: int = 120,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    sequence = 0
    for page in pages:
        tokens = TOKEN_RE.findall(page.text)
        if not tokens:
            continue
        heading = extract_heading(page.text)
        start = 0
        while start < len(tokens):
            end = min(start + target_tokens, len(tokens))
            text = _join_tokens(tokens[start:end])
            for crop in spec.crops:
                chunks.append(
                    Chunk(
                        chunk_id=f"{spec.id}:p{page.page_number}:c{sequence}:{crop}",
                        document_id=spec.id,
                        page_number=page.page_number,
                        sequence=sequence,
                        title=spec.title,
                        heading=heading,
                        text=text,
                        crop=crop,
                        document_type=spec.document_type,
                        advisory_tier=spec.advisory_tier,
                        allowed_use=spec.allowed_use,
                        reviewed=spec.reviewed,
                        source_agency=spec.source_agency,
                        year=spec.year,
                        source_filename=spec.filename,
                    )
                )
            sequence += 1
            if end == len(tokens):
                break
            start = max(end - overlap_tokens, start + 1)
    return chunks


def extract_heading(text: str) -> str:
    for line in text.splitlines():
        candidate = line.strip()
        if 4 <= len(candidate) <= 100 and HEADING_RE.match(candidate):
            return candidate
    return "General"


def _join_tokens(tokens: list[str]) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:%)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    return text.strip()
