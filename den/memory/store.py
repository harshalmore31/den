"""SQLite storage layer for Den agent memory."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid

import numpy as np

from den.memory.config import DenMemoryConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'fact',
    namespace TEXT DEFAULT 'global',
    embedding BLOB,
    strength REAL DEFAULT 1.0,
    access_count INTEGER DEFAULT 0,
    pinned INTEGER DEFAULT 0,
    superseded_by TEXT,
    source_task TEXT,
    created_at REAL,
    last_accessed REAL
);

CREATE TABLE IF NOT EXISTS memory_graph (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    PRIMARY KEY (source_id, target_id)
);

CREATE TABLE IF NOT EXISTS task_history (
    id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL,
    iterations INTEGER DEFAULT 0,
    started_at REAL,
    finished_at REAL,
    summary TEXT,
    phase_data TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_memories_strength ON memories(strength DESC);
CREATE INDEX IF NOT EXISTS idx_task_history_name ON task_history(task_name);
CREATE INDEX IF NOT EXISTS idx_task_history_time ON task_history(started_at DESC);
"""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class MemoryStore:
    """SQLite-backed persistent memory store. Thread-safe."""

    def __init__(self, config: DenMemoryConfig | None = None):
        self.config = config or DenMemoryConfig()
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self.config.db_path), exist_ok=True)
            self._conn = sqlite3.connect(self.config.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def add(
        self,
        content: str,
        category: str = "fact",
        namespace: str = "global",
        embedding: np.ndarray | None = None,
        strength: float | None = None,
        source_task: str = "",
    ) -> str:
        """Store a memory. Returns the memory ID."""
        with self._lock:
            conn = self._get_conn()
            mid = _new_id()
            now = time.time()
            emb_blob = embedding.astype(np.float32).tobytes() if embedding is not None else None
            strength = strength if strength is not None else self.config.initial_strength

            conn.execute(
                "INSERT INTO memories (id, content, category, namespace, embedding, "
                "strength, access_count, source_task, created_at, last_accessed) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (mid, content, category, namespace, emb_blob, strength, source_task, now, now),
            )
            conn.commit()
            return mid

    def get(self, memory_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_all(self, namespace: str | None = None, limit: int = 1000) -> list[dict]:
        conn = self._get_conn()
        if namespace:
            rows = conn.execute(
                "SELECT * FROM memories WHERE namespace = ? "
                "AND superseded_by IS NULL ORDER BY strength DESC LIMIT ?",
                (namespace, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE superseded_by IS NULL "
                "ORDER BY strength DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_text(self, query: str, namespace: str | None = None, limit: int = 20) -> list[dict]:
        conn = self._get_conn()
        if namespace:
            rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? AND namespace = ? "
                "AND superseded_by IS NULL ORDER BY strength DESC LIMIT ?",
                (f"%{query}%", namespace, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? "
                "AND superseded_by IS NULL ORDER BY strength DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_strength(self, memory_id: str, new_strength: float) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE memories SET strength = ?, last_accessed = ? WHERE id = ?",
            (new_strength, time.time(), memory_id),
        )
        conn.commit()

    def increment_access(self, memory_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (time.time(), memory_id),
        )
        conn.commit()

    def supersede(self, old_id: str, new_id: str, weaken_factor: float = 0.5) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE memories SET superseded_by = ?, strength = strength * ? WHERE id = ?",
            (new_id, weaken_factor, old_id),
        )
        conn.commit()

    def decay_all(self, decay_rate: float | None = None) -> None:
        conn = self._get_conn()
        rate = decay_rate or self.config.decay_rate
        conn.execute("UPDATE memories SET strength = strength * ? WHERE pinned = 0", (rate,))
        conn.commit()

    def delete(self, memory_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.execute(
            "DELETE FROM memory_graph WHERE source_id = ? OR target_id = ?",
            (memory_id, memory_id),
        )
        conn.commit()

    def count(self, namespace: str | None = None) -> int:
        conn = self._get_conn()
        if namespace:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE namespace = ? AND superseded_by IS NULL",
                (namespace,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE superseded_by IS NULL"
            ).fetchone()
        return row[0]

    def stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE superseded_by IS NULL"
        ).fetchone()[0]
        if total == 0:
            return {"total": 0, "by_category": {}, "avg_strength": 0.0, "tasks_recorded": 0}

        cats = conn.execute(
            "SELECT category, COUNT(*) FROM memories WHERE superseded_by IS NULL GROUP BY category"
        ).fetchall()
        avg = conn.execute(
            "SELECT AVG(strength) FROM memories WHERE superseded_by IS NULL"
        ).fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]

        return {
            "total": total,
            "by_category": {r[0]: r[1] for r in cats},
            "avg_strength": round(avg or 0, 3),
            "tasks_recorded": tasks,
        }

    def get_all_embeddings(self, namespace: str | None = None) -> tuple[list[str], np.ndarray]:
        conn = self._get_conn()
        if namespace:
            rows = conn.execute(
                "SELECT id, embedding FROM memories WHERE embedding IS NOT NULL "
                "AND (namespace = ? OR namespace = 'global') "
                "AND superseded_by IS NULL ORDER BY strength DESC",
                (namespace,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, embedding FROM memories WHERE embedding IS NOT NULL "
                "AND superseded_by IS NULL ORDER BY strength DESC"
            ).fetchall()

        if not rows:
            return [], np.array([])

        ids = []
        vecs = []
        dim = self.config.embedding_dim
        for r in rows:
            ids.append(r["id"])
            vecs.append(np.frombuffer(r["embedding"], dtype=np.float32).reshape(dim))
        return ids, np.stack(vecs)

    def add_edge(self, source_id: str, target_id: str, weight: float) -> None:
        conn = self._get_conn()
        a, b = (source_id, target_id) if source_id < target_id else (target_id, source_id)
        conn.execute(
            "INSERT INTO memory_graph (source_id, target_id, weight) VALUES (?, ?, ?) "
            "ON CONFLICT(source_id, target_id) DO UPDATE SET weight = MIN(weight + 0.1, 1.0)",
            (a, b, weight),
        )
        conn.commit()

    def get_neighbors(self, memory_id: str) -> list[tuple[str, float]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT source_id, target_id, weight FROM memory_graph "
            "WHERE source_id = ? OR target_id = ?",
            (memory_id, memory_id),
        ).fetchall()
        neighbors = []
        for r in rows:
            other = r["target_id"] if r["source_id"] == memory_id else r["source_id"]
            neighbors.append((other, r["weight"]))
        return neighbors

    def add_task_record(
        self,
        task_name: str,
        status: str,
        iterations: int = 0,
        summary: str = "",
        phase_data: str = "",
    ) -> str:
        conn = self._get_conn()
        tid = _new_id()
        now = time.time()
        conn.execute(
            "INSERT INTO task_history (id, task_name, status, iterations, "
            "started_at, finished_at, summary, phase_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, task_name, status, iterations, now, now, summary, phase_data),
        )
        conn.commit()
        return tid

    def get_task_history(self, task_name: str | None = None, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        if task_name:
            rows = conn.execute(
                "SELECT * FROM task_history WHERE task_name = ? ORDER BY started_at DESC LIMIT ?",
                (task_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM task_history ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("embedding"):
            d["embedding"] = np.frombuffer(
                d["embedding"], dtype=np.float32
            ).reshape(self.config.embedding_dim)
        return d
