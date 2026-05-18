from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3

from anibot.rag.chunking import Chunk
from anibot.rag.manifest import DocumentSpec


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  title TEXT NOT NULL,
  source_agency TEXT NOT NULL,
  document_type TEXT NOT NULL,
  year INTEGER NOT NULL,
  crops TEXT NOT NULL,
  advisory_tier TEXT NOT NULL,
  allowed_use TEXT NOT NULL,
  reviewed INTEGER NOT NULL,
  file_sha256 TEXT NOT NULL,
  indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  sequence INTEGER NOT NULL,
  title TEXT NOT NULL,
  heading TEXT NOT NULL,
  text TEXT NOT NULL,
  crop TEXT NOT NULL,
  document_type TEXT NOT NULL,
  advisory_tier TEXT NOT NULL,
  allowed_use TEXT NOT NULL,
  reviewed INTEGER NOT NULL,
  source_agency TEXT NOT NULL,
  year INTEGER NOT NULL,
  source_filename TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  title,
  heading,
  text
);

CREATE INDEX IF NOT EXISTS idx_chunks_crop_tier ON chunks(crop, advisory_tier, reviewed, allowed_use);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
"""


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    document_id: str
    page_number: int
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
    score: float

    @property
    def citation(self) -> str:
        return f"{self.title}, page {self.page_number}"


class KnowledgeStore:
    def __init__(self, db_path: Path, readonly: bool = False):
        self.db_path = db_path
        if readonly:
            uri = self.db_path.resolve().as_posix()
            self.conn = sqlite3.connect(f"file:{uri}?mode=ro", uri=True)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        if not readonly:
            self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def upsert_document(self, spec: DocumentSpec, pdf_path: Path, chunks: list[Chunk]) -> None:
        digest = sha256_file(pdf_path)
        with self.conn:
            self.conn.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id = ?)", (spec.id,))
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (spec.id,))
            self.conn.execute(
                """
                INSERT INTO documents (
                  id, filename, title, source_agency, document_type, year, crops,
                  advisory_tier, allowed_use, reviewed, file_sha256, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                  filename=excluded.filename,
                  title=excluded.title,
                  source_agency=excluded.source_agency,
                  document_type=excluded.document_type,
                  year=excluded.year,
                  crops=excluded.crops,
                  advisory_tier=excluded.advisory_tier,
                  allowed_use=excluded.allowed_use,
                  reviewed=excluded.reviewed,
                  file_sha256=excluded.file_sha256,
                  indexed_at=CURRENT_TIMESTAMP
                """,
                (
                    spec.id,
                    spec.filename,
                    spec.title,
                    spec.source_agency,
                    spec.document_type,
                    spec.year,
                    ",".join(spec.crops),
                    spec.advisory_tier,
                    spec.allowed_use,
                    int(spec.reviewed),
                    digest,
                ),
            )
            for chunk in chunks:
                self.conn.execute(
                    """
                    INSERT INTO chunks (
                      chunk_id, document_id, page_number, sequence, title, heading, text, crop,
                      document_type, advisory_tier, allowed_use, reviewed, source_agency,
                      year, source_filename
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.page_number,
                        chunk.sequence,
                        chunk.title,
                        chunk.heading,
                        chunk.text,
                        chunk.crop,
                        chunk.document_type,
                        chunk.advisory_tier,
                        chunk.allowed_use,
                        int(chunk.reviewed),
                        chunk.source_agency,
                        chunk.year,
                        chunk.source_filename,
                    ),
                )
                self.conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, title, heading, text) VALUES (?, ?, ?, ?)",
                    (chunk.chunk_id, chunk.title, chunk.heading, chunk.text),
                )

    def prune_absent_documents(self, document_ids: set[str]) -> None:
        placeholders = ",".join("?" for _ in document_ids)
        with self.conn:
            if not document_ids:
                self.conn.execute("DELETE FROM chunks_fts")
                self.conn.execute("DELETE FROM chunks")
                self.conn.execute("DELETE FROM documents")
                return
            rows = self.conn.execute(f"SELECT id FROM documents WHERE id NOT IN ({placeholders})", tuple(document_ids)).fetchall()
            for row in rows:
                self.conn.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id = ?)", (row["id"],))
                self.conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))

    def search(
        self,
        query: str,
        crop: str,
        include_context: bool = False,
        limit: int = 8,
    ) -> list[StoredChunk]:
        allowed_tiers = ["reviewed_advisory"]
        if include_context:
            allowed_tiers.append("context_reference")
        tier_placeholders = ",".join("?" for _ in allowed_tiers)
        fts_query = make_fts_query(query)
        rows = self.conn.execute(
            f"""
            SELECT
              c.*,
              bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
              AND c.reviewed = 1
              AND c.advisory_tier IN ({tier_placeholders})
              AND (c.crop = ? OR c.crop = 'all')
              AND (
                c.allowed_use = 'advisory_evidence'
                OR (? = 1 AND c.allowed_use = 'context_only')
              )
            ORDER BY
              rank ASC,
              CASE c.allowed_use WHEN 'advisory_evidence' THEN 0 ELSE 1 END,
              c.year DESC
            LIMIT ?
            """,
            (fts_query, *allowed_tiers, crop.lower(), int(include_context), limit),
        ).fetchall()
        return [_row_to_chunk(row, score=-float(row["rank"])) for row in rows]

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[StoredChunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = self.conn.execute(f"SELECT *, 0.0 as rank FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_fts_query(query: str) -> str:
    terms = [term for term in query.replace('"', " ").split() if term.strip()]
    if not terms:
        return '"rice"'
    return " OR ".join(f'"{term}"' for term in terms[:12])


def _row_to_chunk(row: sqlite3.Row, score: float) -> StoredChunk:
    return StoredChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        page_number=int(row["page_number"]),
        title=row["title"],
        heading=row["heading"],
        text=row["text"],
        crop=row["crop"],
        document_type=row["document_type"],
        advisory_tier=row["advisory_tier"],
        allowed_use=row["allowed_use"],
        reviewed=bool(row["reviewed"]),
        source_agency=row["source_agency"],
        year=int(row["year"]),
        source_filename=row["source_filename"],
        score=score,
    )
