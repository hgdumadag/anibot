from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from anibot.planning.schema import FarmingPlan, FarmingPlanRequest


SCHEMA = """
CREATE TABLE IF NOT EXISTS farming_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_json TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  status TEXT NOT NULL,
  source_count INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class FarmingPlanRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def save(self, request: FarmingPlanRequest, plan: FarmingPlan) -> int:
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO farming_plans (request_json, plan_json, status, source_count)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request.model_dump_json(),
                    plan.model_dump_json(),
                    plan.status,
                    plan.source_count,
                ),
            )
        return int(cursor.lastrowid)

    def get(self, plan_id: int) -> tuple[FarmingPlanRequest, FarmingPlan] | None:
        row = self.conn.execute("SELECT request_json, plan_json FROM farming_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            return None
        return (
            FarmingPlanRequest.model_validate(json.loads(row["request_json"])),
            FarmingPlan.model_validate(json.loads(row["plan_json"])),
        )

    def latest(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, status, source_count, created_at FROM farming_plans ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
