from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anibot.rag.store import KnowledgeStore, StoredChunk
from anibot.rag.vector import VectorIndex


SUPPORTED_PHASE1_CROPS = {"rice", "corn"}


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    crop: str
    chunks: list[StoredChunk]
    fallback_reason: str | None = None

    @property
    def has_evidence(self) -> bool:
        return bool(self.chunks) and self.fallback_reason is None


def retrieve_evidence(
    query: str,
    crop: str,
    db_path: Path,
    chroma_dir: Path | None = None,
    include_context: bool = False,
    limit: int = 6,
) -> RetrievalResult:
    crop = crop.lower()
    if crop not in SUPPORTED_PHASE1_CROPS:
        return RetrievalResult(
            query=query,
            crop=crop,
            chunks=[],
            fallback_reason=f"{crop} is not supported in Phase 1. Consult the Municipal Agriculture Office.",
        )

    store = KnowledgeStore(db_path, readonly=True)
    try:
        db_limit = limit * 4 if include_context else limit
        fts_chunks = store.search(query=query, crop=crop, include_context=include_context, limit=db_limit)
        vector_chunks: list[StoredChunk] = []
        if chroma_dir is not None:
            vector_ids = VectorIndex(chroma_dir).query(query=query, crop=crop, include_context=include_context, limit=db_limit)
            vector_chunks = store.get_chunks_by_ids(vector_ids)
        chunks = rerank_chunks(fts_chunks, vector_chunks, limit=limit)
        if include_context and chunks and not any(chunk.allowed_use == "context_only" for chunk in chunks):
            context = next((chunk for chunk in fts_chunks if chunk.allowed_use == "context_only"), None)
            if context is not None:
                chunks = [*chunks[: max(limit - 1, 0)], context]
    finally:
        store.close()

    if not chunks:
        return RetrievalResult(
            query=query,
            crop=crop,
            chunks=[],
            fallback_reason="No reviewed source-backed evidence matched this request. Consult the Municipal Agriculture Office.",
        )
    return RetrievalResult(query=query, crop=crop, chunks=chunks)


def rerank_chunks(
    fts_chunks: list[StoredChunk],
    vector_chunks: list[StoredChunk],
    limit: int,
) -> list[StoredChunk]:
    weighted: dict[str, tuple[StoredChunk, float]] = {}
    for rank, chunk in enumerate(fts_chunks):
        metadata_boost = _metadata_boost(chunk)
        weighted[chunk.chunk_id] = (chunk, 100.0 - rank * 3 + metadata_boost + chunk.score)
    for rank, chunk in enumerate(vector_chunks):
        existing = weighted.get(chunk.chunk_id)
        score = 75.0 - rank * 2 + _metadata_boost(chunk)
        if existing:
            weighted[chunk.chunk_id] = (existing[0], existing[1] + score)
        else:
            weighted[chunk.chunk_id] = (chunk, score)
    ranked = sorted(weighted.values(), key=lambda item: item[1], reverse=True)
    return [chunk for chunk, _ in ranked[:limit] if chunk.reviewed and chunk.allowed_use in {"advisory_evidence", "context_only"}]


def require_cited_evidence(cited_chunk_ids: list[str], evidence: list[StoredChunk]) -> tuple[bool, list[str]]:
    evidence_by_id = {chunk.chunk_id: chunk for chunk in evidence}
    invalid: list[str] = []
    for chunk_id in cited_chunk_ids:
        chunk = evidence_by_id.get(chunk_id)
        if chunk is None or not chunk.reviewed or chunk.allowed_use != "advisory_evidence":
            invalid.append(chunk_id)
    return (not invalid, invalid)


def _metadata_boost(chunk: StoredChunk) -> float:
    score = 0.0
    if chunk.allowed_use == "advisory_evidence":
        score += 20.0
    if chunk.advisory_tier == "reviewed_advisory":
        score += 15.0
    if chunk.reviewed:
        score += 10.0
    score += min(max(chunk.year - 2010, 0), 20) * 0.2
    return score
