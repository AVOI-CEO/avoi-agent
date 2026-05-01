"""
second_brain_db.py — SQLite storage engine for Second Brain memory.

Schema:
  memories table with FTS5 full-text search, triggers for auto-sync,
  index for performance, meta table for consolidation summaries.

Adapted for Python stdlib sqlite3 (no better-sqlite3 dependency).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    user_key        TEXT NOT NULL,
    type            TEXT NOT NULL,
    summary         TEXT NOT NULL,
    detail          TEXT,
    scope           TEXT NOT NULL DEFAULT 'durable',
    evidence_kind   TEXT NOT NULL DEFAULT 'inferred',
    source          TEXT NOT NULL DEFAULT 'conversation',
    confidence      REAL NOT NULL,
    importance      REAL NOT NULL,
    durability      REAL NOT NULL,
    evidence_count  INTEGER NOT NULL DEFAULT 1,
    provenance      TEXT,
    dismissed       INTEGER NOT NULL DEFAULT 0,
    superseded_by   TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    last_seen_at    INTEGER NOT NULL,
    last_used_at    INTEGER,
    last_used_query TEXT
);
"""

CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    summary, detail,
    content=memories,
    content_rowid=rowid
);
"""

CREATE_META_TABLE = """
CREATE TABLE IF NOT EXISTS second_brain_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_memories_user_type ON memories(user_key, type);",
    "CREATE INDEX IF NOT EXISTS idx_memories_user_dismissed ON memories(user_key, dismissed);",
    "CREATE INDEX IF NOT EXISTS idx_memories_user_updated  ON memories(user_key, updated_at);",
    "CREATE INDEX IF NOT EXISTS idx_memories_user_scope    ON memories(user_key, scope);",
    "CREATE INDEX IF NOT EXISTS idx_memories_user_evidence  ON memories(user_key, evidence_kind);",
]

CREATE_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, summary, detail)
        VALUES (new.rowid, new.summary, new.detail);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, summary, detail)
        VALUES ('delete', old.rowid, old.summary, old.detail);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, summary, detail)
        VALUES ('delete', old.rowid, old.summary, old.detail);
        INSERT INTO memories_fts(rowid, summary, detail)
        VALUES (new.rowid, new.summary, new.detail);
    END;
    """,
]


# ---------------------------------------------------------------------------
# Column names for UPDATE (subset that can be mutated)
# ---------------------------------------------------------------------------
_MUTABLE_FIELDS = frozenset({
    "summary", "detail", "scope", "evidence_kind", "source",
    "confidence", "importance", "durability", "evidence_count",
    "provenance", "dismissed", "superseded_by",
    "updated_at", "last_seen_at", "last_used_at", "last_used_query",
})


# ---------------------------------------------------------------------------
# SecondBrainDB
# ---------------------------------------------------------------------------

class SecondBrainDB:
    """SQLite-backed storage with FTS5 search, merge, conflict, and pruning."""

    def __init__(self, db_path: str | Path):
        import sqlite3
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local connection. Each thread gets its own."""
        import sqlite3
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn
        return self._local.conn

    def init(self) -> None:
        """Create schema, indexes, FTS5, triggers."""
        cur = self._get_conn().cursor()
        cur.execute(CREATE_MEMORIES_TABLE)
        cur.execute(CREATE_FTS_TABLE)
        cur.execute(CREATE_META_TABLE)
        for idx in CREATE_INDEXES:
            cur.execute(idx)
        for trig in CREATE_TRIGGERS:
            try:
                cur.execute(trig)
            except Exception as e:
                logger.debug("Trigger creation (may already exist): %s", e)
        self._get_conn().commit()
        logger.info("Second brain database initialized at %s", self._db_path)

    # -- CRUD ----------------------------------------------------------------

    def insert(self, row: Dict[str, Any]) -> None:
        """Insert a memory row."""
        self._get_conn().execute("""
            INSERT INTO memories (
                id, user_key, type, summary, detail, scope, evidence_kind, source,
                confidence, importance, durability, evidence_count, provenance,
                dismissed, superseded_by, created_at, updated_at,
                last_seen_at, last_used_at, last_used_query
            ) VALUES (
                :id, :user_key, :type, :summary, :detail, :scope, :evidence_kind, :source,
                :confidence, :importance, :durability, :evidence_count, :provenance,
                :dismissed, :superseded_by, :created_at, :updated_at,
                :last_seen_at, :last_used_at, :last_used_query
            )
        """, {
            "id": row["id"],
            "user_key": row.get("user_key", "user:owner"),
            "type": row["type"],
            "summary": row["summary"],
            "detail": row.get("detail"),
            "scope": row.get("scope", "durable"),
            "evidence_kind": row.get("evidence_kind", "inferred"),
            "source": row.get("source", "conversation"),
            "confidence": row["confidence"],
            "importance": row["importance"],
            "durability": row["durability"],
            "evidence_count": row.get("evidence_count", 1),
            "provenance": row.get("provenance"),
            "dismissed": row.get("dismissed", 0),
            "superseded_by": row.get("superseded_by"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_seen_at": row["last_seen_at"],
            "last_used_at": row.get("last_used_at"),
            "last_used_query": row.get("last_used_query"),
        })
        self._get_conn().commit()

    def update(self, row: Dict[str, Any]) -> None:
        """Partial update of mutable fields. `id` is required."""
        fields = []
        values = {"id": row["id"]}
        for f in _MUTABLE_FIELDS:
            if f in row and row[f] is not None:
                fields.append(f"{f} = :{f}")
                values[f] = row[f]
        if not fields:
            return
        self._get_conn().execute(
            f"UPDATE memories SET {', '.join(fields)} WHERE id = :id",
            values,
        )
        self._get_conn().commit()

    def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        cur = self._get_conn().execute(
            "SELECT * FROM memories WHERE id = ?", (id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_active(self, user_key: str = "user:owner") -> List[Dict[str, Any]]:
        cur = self._get_conn().execute(
            "SELECT * FROM memories WHERE user_key = ? AND dismissed = 0 ORDER BY updated_at DESC",
            (user_key,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_by_type(self, user_key: str, type: str) -> List[Dict[str, Any]]:
        cur = self._get_conn().execute(
            "SELECT * FROM memories WHERE user_key = ? AND type = ? AND dismissed = 0 ORDER BY updated_at DESC",
            (user_key, type),
        )
        return [dict(r) for r in cur.fetchall()]

    # -- FTS5 Search ---------------------------------------------------------

    def search_relevant(
        self,
        user_key: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """FTS5 full-text search with fallback to LIKE."""
        tokens = [t for t in query.split() if len(t) > 0]
        if not tokens:
            cur = self._get_conn().execute(
                "SELECT * FROM memories WHERE user_key = ? AND dismissed = 0 ORDER BY updated_at DESC LIMIT ?",
                (user_key, limit),
            )
            return [dict(r) for r in cur.fetchall()]

        fts_query = " OR ".join(tokens)
        try:
            cur = self._get_conn().execute(
                """
                SELECT m.* FROM memories m
                JOIN memories_fts fts ON m.rowid = fts.rowid
                WHERE memories_fts MATCH ? AND m.user_key = ? AND m.dismissed = 0
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, user_key, limit),
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            # FTS5 fallback: LIKE scan
            clauses = " OR ".join(["(summary LIKE ? OR detail LIKE ?)" for _ in tokens])
            likes = [t.strip('"') for t in tokens]
            params = [user_key]
            for t in likes:
                params.append(f"%{t}%")
                params.append(f"%{t}%")
            params.append(limit)
            cur = self._get_conn().execute(
                f"SELECT * FROM memories WHERE user_key = ? AND dismissed = 0 AND ({clauses}) ORDER BY updated_at DESC LIMIT ?",
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def search_fts(
        self,
        user_key: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.search_relevant(user_key, query, limit)

    # -- Merge / conflict detection ------------------------------------------

    def find_merge_candidate(
        self,
        user_key: str,
        type: str,
        normalized_terms: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Find an existing memory that could absorb a new one via merge."""
        if not normalized_terms:
            return None
        like_any = [f"%{t}%" for t in normalized_terms[:3]]
        params = [user_key, type] + like_any[:1] + like_any
        cur = self._get_conn().execute(
            """
            SELECT * FROM memories
            WHERE user_key = ? AND type = ? AND dismissed = 0
            AND (summary LIKE ? OR {})
            LIMIT 5
            """.format(" OR ".join("summary LIKE ?" for _ in like_any)),
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            if not _row_has_negation_mismatch(row["summary"], normalized_terms):
                return row
        return None

    def find_conflict_candidate(
        self,
        user_key: str,
        type: str,
        summary_terms: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Find an existing memory with opposing polarity (likes vs dislikes)."""
        if not summary_terms:
            return None
        likes = [f"%{t}%" for t in summary_terms]
        params = [user_key, type] + likes
        cur = self._get_conn().execute(
            "SELECT * FROM memories WHERE user_key = ? AND type = ? AND dismissed = 0 AND ("
            + " OR ".join("summary LIKE ?" for _ in likes)
            + ") LIMIT 5",
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            if _row_has_negation_mismatch(row["summary"], summary_terms):
                return row
        return None

    # -- Soft delete / promote / prune ---------------------------------------

    def soft_delete(self, id: str) -> bool:
        self._get_conn().execute(
            "UPDATE memories SET dismissed = 1, updated_at = ? WHERE id = ?",
            (int(time.time() * 1000), id),
        )
        self._get_conn().commit()
        return True

    def clear_by_type(self, user_key: str, type: Optional[str] = None) -> int:
        now = int(time.time() * 1000)
        if type:
            cur = self._get_conn().execute(
                "UPDATE memories SET dismissed = 1, updated_at = ? WHERE user_key = ? AND type = ? AND dismissed = 0",
                (now, user_key, type),
            )
        else:
            cur = self._get_conn().execute(
                "UPDATE memories SET dismissed = 1, updated_at = ? WHERE user_key = ? AND dismissed = 0",
                (now, user_key),
            )
        self._get_conn().commit()
        return cur.rowcount

    def hard_delete_dismissed(self, user_key: str) -> int:
        cur = self._get_conn().execute(
            "DELETE FROM memories WHERE user_key = ? AND dismissed = 1",
            (user_key,),
        )
        self._get_conn().commit()
        return cur.rowcount

    def promote_to_durable(self, user_key: str) -> int:
        now = int(time.time() * 1000)
        cur = self._get_conn().execute(
            """
            UPDATE memories SET scope = 'durable', updated_at = ?
            WHERE user_key = ? AND scope = 'active' AND dismissed = 0
              AND evidence_count >= 3 AND evidence_kind IN ('direct', 'manual')
            """,
            (now, user_key),
        )
        self._get_conn().commit()
        return cur.rowcount

    def prune_stale(self, user_key: str) -> Tuple[int, int]:
        """
        Prune stale memories.
        Returns (active_pruned, durable_pruned).
        """
        now = int(time.time() * 1000)
        day_ms = 24 * 60 * 60 * 1000
        twenty_one_days = 21 * day_ms
        forty_two_days = 42 * day_ms
        one_hundred_twenty_days = 120 * day_ms

        # Active inferred: stale after 21 days
        c1 = self._get_conn().execute(
            "UPDATE memories SET dismissed = 1, updated_at = ? WHERE user_key = ? AND scope = 'active' AND evidence_kind = 'inferred' AND dismissed = 0 AND last_seen_at > 0 AND last_seen_at < ?",
            (now, user_key, now - twenty_one_days),
        )
        # Active direct: stale after 42 days
        c2 = self._get_conn().execute(
            "UPDATE memories SET dismissed = 1, updated_at = ? WHERE user_key = ? AND scope = 'active' AND evidence_kind = 'direct' AND dismissed = 0 AND last_seen_at > 0 AND last_seen_at < ?",
            (now, user_key, now - forty_two_days),
        )
        active_pruned = c1.rowcount + c2.rowcount

        # Durable inferred: decay confidence after 120 days
        self._get_conn().execute(
            "UPDATE memories SET confidence = MAX(0.15, confidence - 0.15), updated_at = ? WHERE user_key = ? AND scope = 'durable' AND evidence_kind = 'inferred' AND dismissed = 0 AND last_seen_at > 0 AND last_seen_at < ?",
            (now, user_key, now - one_hundred_twenty_days),
        )
        # Durable with decayed confidence: dismiss
        c3 = self._get_conn().execute(
            "UPDATE memories SET dismissed = 1, updated_at = ? WHERE user_key = ? AND scope = 'durable' AND dismissed = 0 AND confidence < 0.3 AND last_seen_at > 0 AND last_seen_at < ?",
            (now, user_key, now - one_hundred_twenty_days),
        )
        durable_pruned = c3.rowcount

        self._get_conn().commit()
        return active_pruned, durable_pruned

    # -- Meta key-value store ------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        self._get_conn().execute(
            "INSERT OR REPLACE INTO second_brain_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._get_conn().commit()

    def get_meta(self, key: str) -> Optional[str]:
        cur = self._get_conn().execute(
            "SELECT value FROM second_brain_meta WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row["value"] if row else None

    def delete_meta(self, key: str) -> None:
        self._get_conn().execute("DELETE FROM second_brain_meta WHERE key = ?", (key,))
        self._get_conn().commit()

    # -- Stats ---------------------------------------------------------------

    def count_by_type(self, user_key: str = "user:owner") -> Dict[str, int]:
        cur = self._get_conn().execute(
            "SELECT type, COUNT(*) as count FROM memories WHERE user_key = ? AND dismissed = 0 GROUP BY type",
            (user_key,),
        )
        return {r["type"]: r["count"] for r in cur.fetchall()}

    def total_active(self, user_key: str = "user:owner") -> int:
        cur = self._get_conn().execute(
            "SELECT COUNT(*) as count FROM memories WHERE user_key = ? AND dismissed = 0",
            (user_key,),
        )
        return cur.fetchone()["count"]

    # -- Close ---------------------------------------------------------------

    def close(self) -> None:
        """Close all thread-local connections."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_NEGATION_WORDS = {"not", "never", "no longer", "avoid", "against", "disabled"}


def _row_has_negation_mismatch(existing_summary: str, incoming_terms: List[str]) -> bool:
    """Check if existing memory's sentiment differs from incoming terms."""
    lower = existing_summary.lower()
    has_negation = any(w in lower for w in _NEGATION_WORDS)
    incoming_lower = " ".join(incoming_terms).lower()
    incoming_has_negation = any(w in incoming_lower for w in _NEGATION_WORDS)
    return has_negation != incoming_has_negation
