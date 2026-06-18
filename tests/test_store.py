"""Tests for NormStore."""
from __future__ import annotations

import os
import tempfile

from normsync.norm import NormRevision, NormViolation, WorldNorm
from normsync.store import NormStore


def make_norm(name: str = "test-norm") -> WorldNorm:
    return WorldNorm(name=name, description="desc", condition="safe_zone", prohibited="attack")


def make_violation(norm_id: str = "norm1") -> NormViolation:
    return NormViolation(
        norm_id=norm_id,
        norm_name="test-norm",
        action_id="act1",
        agent_id="agent1",
        description="Violated test norm",
        timestamp=1.0,
    )


def make_revision(norm_id: str = "norm1") -> NormRevision:
    return NormRevision(norm_id=norm_id, revision_type="create", reason="init", timestamp=1.0)


class TestNormStore:
    def test_save_and_get_norms(self):
        store = NormStore()
        norm = make_norm()
        store.save_norm(norm)
        norms = store.get_norms()
        assert len(norms) == 1
        assert norms[0].name == "test-norm"

    def test_get_norms_active_only(self):
        store = NormStore()
        norm1 = make_norm("active-norm")
        norm2 = make_norm("inactive-norm")
        norm2.active = False
        store.save_norm(norm1)
        store.save_norm(norm2)
        active = store.get_norms(active_only=True)
        assert len(active) == 1
        assert active[0].name == "active-norm"

    def test_save_and_get_violations(self):
        store = NormStore()
        v = make_violation()
        store.save_violation(v)
        violations = store.get_violations()
        assert len(violations) == 1
        assert violations[0].agent_id == "agent1"

    def test_save_and_get_revisions(self):
        store = NormStore()
        rev = make_revision()
        store.save_revision(rev)
        revisions = store.get_revisions()
        assert len(revisions) == 1
        assert revisions[0].revision_type == "create"

    def test_in_memory_db(self):
        store = NormStore(":memory:")
        norm = make_norm()
        store.save_norm(norm)
        assert len(store.get_norms()) == 1

    def test_file_based_db_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store1 = NormStore(db_path)
            norm = make_norm("persistent-norm")
            store1.save_norm(norm)
            store1.close()

            store2 = NormStore(db_path)
            norms = store2.get_norms()
            store2.close()
            assert len(norms) == 1
            assert norms[0].name == "persistent-norm"
        finally:
            os.unlink(db_path)

    def test_multiple_norms(self):
        store = NormStore()
        for i in range(5):
            store.save_norm(make_norm(f"norm-{i}"))
        assert len(store.get_norms()) == 5

    def test_violations_ordered_by_timestamp_desc(self):
        store = NormStore()
        v1 = NormViolation("n", "name", "a1", "agent", "desc", timestamp=1.0)
        v2 = NormViolation("n", "name", "a2", "agent", "desc", timestamp=3.0)
        v3 = NormViolation("n", "name", "a3", "agent", "desc", timestamp=2.0)
        store.save_violation(v1)
        store.save_violation(v2)
        store.save_violation(v3)
        violations = store.get_violations()
        assert violations[0].timestamp == 3.0
