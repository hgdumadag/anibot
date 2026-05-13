from __future__ import annotations

from pathlib import Path
import hashlib

from anibot.rag.chunking import Chunk


class VectorIndex:
    """Optional Chroma-backed vector index.

    The SQLite FTS index is the guaranteed offline search path. If Chroma is
    installed, this class also writes embeddings using a deterministic local
    hash embedding so indexing does not require model downloads.
    """

    def __init__(self, persist_dir: Path, collection_name: str = "anibot_knowledge"):
        self.available = False
        self.collection = None
        try:
            import chromadb  # type: ignore
        except ImportError:
            return

        persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = client.get_or_create_collection(collection_name)
        self.available = True

    def upsert_document_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        if not self.available or self.collection is None:
            return
        existing = self.collection.get(where={"document_id": document_id}, include=[])
        if existing.get("ids"):
            self.collection.delete(ids=existing["ids"])
        if not chunks:
            return
        self.collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[hash_embedding(chunk.text) for chunk in chunks],
            metadatas=[
                {
                    "document_id": chunk.document_id,
                    "crop": chunk.crop,
                    "advisory_tier": chunk.advisory_tier,
                    "allowed_use": chunk.allowed_use,
                    "reviewed": chunk.reviewed,
                    "page_number": chunk.page_number,
                    "year": chunk.year,
                }
                for chunk in chunks
            ],
        )

    def query(self, query: str, crop: str, include_context: bool, limit: int) -> list[str]:
        if not self.available or self.collection is None:
            return []
        tiers = ["reviewed_advisory"]
        if include_context:
            tiers.append("context_reference")
        where = {
            "$and": [
                {"reviewed": True},
                {"advisory_tier": {"$in": tiers}},
                {"crop": {"$in": [crop.lower(), "all"]}},
            ]
        }
        result = self.collection.query(
            query_embeddings=[hash_embedding(query)],
            n_results=limit,
            where=where,
            include=[],
        )
        return list(result.get("ids", [[]])[0])


def hash_embedding(text: str, dimensions: int = 128) -> list[float]:
    values = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[bucket] += sign
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return [value / norm for value in values]
