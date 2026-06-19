"""Norm versioning — track the full history of norm changes."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from normsync.norm import WorldNorm
from normsync.store import NormStore


@dataclass
class NormVersion:
    norm_id: str
    norm_name: str
    version: int
    changed_at: float  # timestamp
    changed_by: str  # agent or human ID
    change_reason: str
    previous_version: int | None


class NormVersionStore:
    """Track the history of norm changes using an extra SQLite table on the NormStore's DB."""

    def __init__(self, store: NormStore) -> None:
        self._store = store
        self._conn = store._conn  # reuse the same connection
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS norm_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                norm_id TEXT NOT NULL,
                norm_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL,
                change_reason TEXT NOT NULL,
                previous_version INTEGER,
                norm_snapshot TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def record_change(self, norm: WorldNorm, changed_by: str, reason: str) -> NormVersion:
        """Record a norm change. Version auto-increments per norm."""
        # Find current max version for this norm
        row = self._conn.execute(
            "SELECT MAX(version) FROM norm_versions WHERE norm_id=?", (norm.id,)
        ).fetchone()
        prev = row[0]  # None if first version
        version = (prev or 0) + 1
        now = time.time()
        cols = (
            "norm_id, norm_name, version, changed_at, "
            "changed_by, change_reason, previous_version, norm_snapshot"
        )
        self._conn.execute(
            f"INSERT INTO norm_versions ({cols}) VALUES (?,?,?,?,?,?,?,?)",  # noqa: S608  # nosec B608
            (
                norm.id,
                norm.name,
                version,
                now,
                changed_by,
                reason,
                prev,
                json.dumps(norm.to_dict()),
            ),
        )
        self._conn.commit()
        return NormVersion(
            norm_id=norm.id,
            norm_name=norm.name,
            version=version,
            changed_at=now,
            changed_by=changed_by,
            change_reason=reason,
            previous_version=prev,
        )

    def get_history(self, norm_name: str) -> list[NormVersion]:
        """Return all versions of a norm by name, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM norm_versions WHERE norm_name=? ORDER BY version DESC",
            (norm_name,),
        ).fetchall()
        result = []
        for r in rows:
            result.append(
                NormVersion(
                    norm_id=r["norm_id"],
                    norm_name=r["norm_name"],
                    version=r["version"],
                    changed_at=r["changed_at"],
                    changed_by=r["changed_by"],
                    change_reason=r["change_reason"],
                    previous_version=r["previous_version"],
                )
            )
        return result

    def get_norm_at(self, norm_name: str, timestamp: float) -> WorldNorm | None:
        """Get what a norm looked like at a specific point in time."""
        row = self._conn.execute(
            """SELECT norm_snapshot FROM norm_versions
               WHERE norm_name=? AND changed_at <= ? ORDER BY changed_at DESC LIMIT 1""",
            (norm_name, timestamp),
        ).fetchone()
        if row is None:
            return None
        return WorldNorm.from_dict(json.loads(row["norm_snapshot"]))

    def diff_versions(self, norm_name: str, v1: int, v2: int) -> dict[str, Any]:
        """Show what changed between two versions. Returns dict with changed fields."""
        sql = (
            "SELECT version, norm_snapshot FROM norm_versions "
            "WHERE norm_name=? AND version IN (?,?)"
        )
        rows = self._conn.execute(sql, (norm_name, v1, v2)).fetchall()
        snaps = {r["version"]: json.loads(r["norm_snapshot"]) for r in rows}
        if v1 not in snaps or v2 not in snaps:
            return {"error": f"Version(s) not found for norm '{norm_name}'"}
        s1, s2 = snaps[v1], snaps[v2]
        diff: dict[str, Any] = {}
        for key in set(list(s1.keys()) + list(s2.keys())):
            if s1.get(key) != s2.get(key):
                diff[key] = {"v1": s1.get(key), "v2": s2.get(key)}
        return diff
