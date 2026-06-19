"""SQLite-backed persistence for norms, violations, and revisions."""

from __future__ import annotations

import sqlite3

from normsync.norm import NormRevision, NormViolation, WorldNorm


class NormStore:
    """SQLite-backed persistence for norms, violations, and revisions."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS norms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                condition TEXT,
                prohibited TEXT,
                scope TEXT DEFAULT 'global',
                active INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS violations (
                id TEXT PRIMARY KEY,
                norm_id TEXT,
                norm_name TEXT,
                action_id TEXT,
                agent_id TEXT,
                description TEXT,
                severity TEXT DEFAULT 'warn',
                timestamp REAL
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY,
                norm_id TEXT,
                revision_type TEXT,
                reason TEXT,
                timestamp REAL
            );
        """)
        self._conn.commit()

    def save_norm(self, norm: WorldNorm) -> None:
        """Persist a norm (insert or replace)."""
        self._conn.execute(
            "INSERT OR REPLACE INTO norms VALUES (?,?,?,?,?,?,?,?)",
            (
                norm.id,
                norm.name,
                norm.description,
                norm.condition,
                norm.prohibited,
                norm.scope,
                int(norm.active),
                norm.priority,
            ),
        )
        self._conn.commit()

    def get_norms(self, active_only: bool = False) -> list[WorldNorm]:
        """Retrieve all (or only active) norms."""
        sql = "SELECT * FROM norms"
        if active_only:
            sql += " WHERE active = 1"
        rows = self._conn.execute(sql).fetchall()
        result = []
        for r in rows:
            n = WorldNorm(
                name=r["name"],
                description=r["description"],
                condition=r["condition"],
                prohibited=r["prohibited"],
                scope=r["scope"],
                active=bool(r["active"]),
                priority=r["priority"],
            )
            result.append(n)
        return result

    def save_violation(self, v: NormViolation) -> None:
        """Persist a norm violation."""
        self._conn.execute(
            "INSERT OR REPLACE INTO violations VALUES (?,?,?,?,?,?,?,?)",
            (
                v.id,
                v.norm_id,
                v.norm_name,
                v.action_id,
                v.agent_id,
                v.description,
                v.severity,
                v.timestamp,
            ),
        )
        self._conn.commit()

    def get_violations(self) -> list[NormViolation]:
        """Retrieve all violations ordered by timestamp descending."""
        rows = self._conn.execute("SELECT * FROM violations ORDER BY timestamp DESC").fetchall()
        result = []
        for r in rows:
            v = NormViolation(
                norm_id=r["norm_id"],
                norm_name=r["norm_name"],
                action_id=r["action_id"],
                agent_id=r["agent_id"],
                description=r["description"],
                severity=r["severity"],
                timestamp=r["timestamp"],
            )
            result.append(v)
        return result

    def save_revision(self, rev: NormRevision) -> None:
        """Persist a norm revision."""
        self._conn.execute(
            "INSERT OR REPLACE INTO revisions VALUES (?,?,?,?,?)",
            (rev.id, rev.norm_id, rev.revision_type, rev.reason, rev.timestamp),
        )
        self._conn.commit()

    def get_revisions(self) -> list[NormRevision]:
        """Retrieve all revisions ordered by timestamp descending."""
        rows = self._conn.execute("SELECT * FROM revisions ORDER BY timestamp DESC").fetchall()
        result = []
        for r in rows:
            rev = NormRevision(
                norm_id=r["norm_id"],
                revision_type=r["revision_type"],
                reason=r["reason"],
                timestamp=r["timestamp"],
            )
            result.append(rev)
        return result

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
