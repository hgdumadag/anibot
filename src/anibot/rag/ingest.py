from __future__ import annotations

import argparse
from pathlib import Path

from anibot.rag.chunking import chunk_document
from anibot.rag.manifest import load_manifest
from anibot.rag.pdf_extract import extract_pdf_pages
from anibot.rag.store import KnowledgeStore
from anibot.rag.vector import VectorIndex


def ingest_knowledge(
    repo_root: Path,
    manifest_path: Path | None = None,
    docs_dir: Path | None = None,
    db_path: Path | None = None,
    chroma_dir: Path | None = None,
) -> dict[str, int | bool]:
    manifest_path = manifest_path or repo_root / "knowledge" / "manifest.toml"
    docs_dir = docs_dir or repo_root / "docs"
    db_path = db_path or repo_root / "data" / "anibot_knowledge.db"
    chroma_dir = chroma_dir or repo_root / "data" / "chroma"

    specs = load_manifest(manifest_path)
    store = KnowledgeStore(db_path)
    vector = VectorIndex(chroma_dir)

    documents = 0
    chunks_total = 0
    try:
        for spec in specs:
            pdf_path = docs_dir / spec.filename
            if not pdf_path.exists():
                raise FileNotFoundError(f"Manifest document not found: {pdf_path}")
            pages = extract_pdf_pages(pdf_path)
            chunks = chunk_document(spec, pages)
            store.upsert_document(spec, pdf_path, chunks)
            vector.upsert_document_chunks(spec.id, chunks)
            documents += 1
            chunks_total += len(chunks)
        store.prune_absent_documents({spec.id for spec in specs})
    finally:
        store.close()

    return {
        "documents": documents,
        "chunks": chunks_total,
        "chroma_enabled": vector.available,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest AniBot PDF knowledge into local indexes.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--docs-dir", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--chroma-dir", type=Path)
    args = parser.parse_args()

    result = ingest_knowledge(
        repo_root=args.repo_root,
        manifest_path=args.manifest,
        docs_dir=args.docs_dir,
        db_path=args.db,
        chroma_dir=args.chroma_dir,
    )
    print(
        f"Indexed {result['documents']} documents into {result['chunks']} chunks "
        f"(chroma_enabled={result['chroma_enabled']})."
    )


if __name__ == "__main__":
    main()
