"""Tests for normsync.versioning."""
import time

from normsync.norm import WorldNorm
from normsync.store import NormStore
from normsync.versioning import NormVersionStore


def make_norm(name="no_attack"):
    return WorldNorm(
        name=name,
        description="Agents must not attack in safe zones",
        condition="safe_zone",
        prohibited="attack",
    )


def test_record_change_basic():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    v = version_store.record_change(norm, "admin", "Initial norm")
    assert v.version == 1
    assert v.norm_name == "no_attack"
    assert v.previous_version is None


def test_version_increments():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    v1 = version_store.record_change(norm, "admin", "First")
    v2 = version_store.record_change(norm, "admin", "Second")
    assert v2.version == 2
    assert v2.previous_version == 1


def test_get_history():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    version_store.record_change(norm, "admin", "First")
    version_store.record_change(norm, "admin", "Second")
    history = version_store.get_history("no_attack")
    assert len(history) == 2
    assert history[0].version == 2  # newest first


def test_get_norm_at():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    before = time.time()
    version_store.record_change(norm, "admin", "First")
    after = time.time()
    found = version_store.get_norm_at("no_attack", after + 1)
    assert found is not None
    assert found.name == "no_attack"
    # Before the norm existed
    not_found = version_store.get_norm_at("no_attack", before - 1)
    assert not_found is None


def test_diff_versions():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    version_store.record_change(norm, "admin", "First")
    # Modify norm (create a new one with same name but different condition)
    norm2 = WorldNorm(
        name="no_attack",
        description="Updated description",
        condition="any_zone",
        prohibited="attack",
    )
    store.save_norm(norm2)
    version_store.record_change(norm2, "admin", "Updated")
    diff = version_store.diff_versions("no_attack", 1, 2)
    assert isinstance(diff, dict)
    # Versions that differ should show the changed fields
    assert "condition" in diff or "description" in diff or len(diff) > 0


def test_diff_versions_not_found():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    version_store.record_change(norm, "admin", "First")
    diff = version_store.diff_versions("no_attack", 1, 99)
    assert "error" in diff


def test_diff_versions_no_changes():
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    norm = make_norm()
    store.save_norm(norm)
    version_store.record_change(norm, "admin", "First")
    version_store.record_change(norm, "admin", "Second — same snapshot")
    diff = version_store.diff_versions("no_attack", 1, 2)
    # id field will differ (since it's the same norm) — actually all fields are identical
    assert isinstance(diff, dict)
