from __future__ import annotations

from pathlib import Path
import sqlite3

from anibot.rag.ingest import ingest_knowledge
from anibot.rag.manifest import load_manifest
from anibot.rag.retriever import require_cited_evidence, retrieve_evidence


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_classifies_documents() -> None:
    docs = load_manifest(ROOT / "knowledge" / "manifest.toml")
    by_id = {doc.id: doc for doc in docs}

    assert by_id["pns_bafs_141_2019_rice_gap"].supports_advisory
    assert by_id["pagasa_monthly_agroclimatic_2026_03"].allowed_use == "context_only"
    assert by_id["pns_bafs_20_2018_corn_gap"].supports_advisory


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    chroma_dir = tmp_path / "chroma"

    first = ingest_knowledge(ROOT, db_path=db_path, chroma_dir=chroma_dir)
    second = ingest_knowledge(ROOT, db_path=db_path, chroma_dir=chroma_dir)

    assert first["documents"] == second["documents"] == 10
    assert first["chunks"] == second["chunks"]
    with sqlite3.connect(db_path) as conn:
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        distinct_count = conn.execute("SELECT COUNT(DISTINCT chunk_id) FROM chunks").fetchone()[0]
    assert chunk_count == distinct_count == second["chunks"]


def test_rice_retrieval_excludes_context_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")

    result = retrieve_evidence("water management seed preparation rice", "rice", db_path)

    assert result.fallback_reason is None
    assert result.chunks
    assert all(chunk.crop == "rice" for chunk in result.chunks)
    assert all(chunk.allowed_use == "advisory_evidence" for chunk in result.chunks)
    assert all(chunk.reviewed for chunk in result.chunks)


def test_context_retrieval_requires_explicit_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")

    without_context = retrieve_evidence("soil moisture rainfall PAGASA", "rice", db_path, include_context=False)
    with_context = retrieve_evidence("soil moisture rainfall PAGASA", "rice", db_path, include_context=True)

    assert all(chunk.allowed_use == "advisory_evidence" for chunk in without_context.chunks)
    assert any(chunk.allowed_use == "context_only" for chunk in with_context.chunks)


def test_corn_retrieval_uses_reviewed_corn_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")

    result = retrieve_evidence("corn pest management", "corn", db_path)

    assert result.fallback_reason is None
    assert result.chunks
    assert all(chunk.crop == "corn" for chunk in result.chunks)
    assert all(chunk.allowed_use == "advisory_evidence" for chunk in result.chunks)
    assert all(chunk.reviewed for chunk in result.chunks)


def test_citation_integrity_rejects_context_and_unknown_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")
    result = retrieve_evidence("rainfall soil moisture", "rice", db_path, include_context=True)

    context = next(chunk for chunk in result.chunks if chunk.allowed_use == "context_only")
    valid = next(chunk for chunk in result.chunks if chunk.allowed_use == "advisory_evidence")

    ok, invalid = require_cited_evidence([valid.chunk_id, context.chunk_id, "missing"], result.chunks)

    assert ok is False
    assert context.chunk_id in invalid
    assert "missing" in invalid


def test_deleted_manifest_document_is_pruned(tmp_path: Path) -> None:
    manifest_src = ROOT / "knowledge" / "manifest.toml"
    manifest_copy = tmp_path / "manifest.toml"
    text = manifest_src.read_text(encoding="utf-8")
    cutoff = text.index('[[documents]]\nid = "pns_bafs_20_2018_corn_gap"')
    manifest_copy.write_text(text[:cutoff], encoding="utf-8")

    db_path = tmp_path / "knowledge.db"
    ingest_knowledge(ROOT, db_path=db_path, chroma_dir=tmp_path / "chroma")
    ingest_knowledge(ROOT, manifest_path=manifest_copy, db_path=db_path, chroma_dir=tmp_path / "chroma")

    with sqlite3.connect(db_path) as conn:
        ids = {row[0] for row in conn.execute("SELECT id FROM documents")}

    assert "pns_bafs_20_2018_corn_gap" not in ids
    assert ids == {
        "pns_bafs_141_2019_rice_gap",
        "pns_bafs_42_2019_organic_milled_rice_gap",
        "pns_bafs_319_2021_traditional_rice_organic",
        "pagasa_monthly_agroclimatic_2026_03",
        "bswm_map_guidebook_2024",
    }
