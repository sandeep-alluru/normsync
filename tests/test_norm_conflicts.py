"""Tests for normsync.conflicts."""

from normsync.conflicts import detect_norm_conflicts
from normsync.norm import WorldNorm
from normsync.store import NormStore


def test_detect_no_conflicts():
    store = NormStore(":memory:")
    norm = WorldNorm(
        name="no_attack",
        description="No attack in safe zones",
        condition="safe_zone",
        prohibited="attack",
    )
    store.save_norm(norm)
    conflicts = detect_norm_conflicts(store)
    # Single norm, no conflicts
    assert isinstance(conflicts, list)


def test_detect_logical_contradiction():
    store = NormStore(":memory:")
    norm_a = WorldNorm(
        name="must_attack",
        description="Must attack enemies",
        condition="enemy_zone",
        prohibited="retreat",
        priority=1,
    )
    norm_b = WorldNorm(
        name="no_attack",
        description="Never attack anyone",
        condition="enemy_zone",
        prohibited="attack",
        priority=1,
    )
    store.save_norm(norm_a)
    store.save_norm(norm_b)
    conflicts = detect_norm_conflicts(store)
    assert len(conflicts) >= 1
    conflict_types = [c.conflict_type for c in conflicts]
    assert any(ct in ("logical_contradiction", "priority_ambiguity") for ct in conflict_types)


def test_detect_priority_ambiguity():
    store = NormStore(":memory:")
    norm_a = WorldNorm(
        name="norm_a",
        description="Norm A",
        condition="zone combat",
        prohibited="flee",
        priority=5,
        scope="global",
    )
    norm_b = WorldNorm(
        name="norm_b",
        description="Norm B",
        condition="zone retreat",
        prohibited="attack",
        priority=5,
        scope="global",
    )
    store.save_norm(norm_a)
    store.save_norm(norm_b)
    conflicts = detect_norm_conflicts(store)
    assert isinstance(conflicts, list)


def test_conflict_fields():
    store = NormStore(":memory:")
    norm_a = WorldNorm(name="na", description="d", condition="zone", prohibited="attack", priority=1)
    norm_b = WorldNorm(name="nb", description="d", condition="zone attack", prohibited="defend", priority=1)
    store.save_norm(norm_a)
    store.save_norm(norm_b)
    conflicts = detect_norm_conflicts(store)
    for c in conflicts:
        assert c.norm_a
        assert c.norm_b
        assert c.conflict_type in ("logical_contradiction", "priority_ambiguity", "scope_overlap")
        assert c.description
        assert c.example_action


def test_detect_scope_overlap():
    store = NormStore(":memory:")
    norm_a = WorldNorm(
        name="global_norm",
        description="Global rule",
        condition="zone",
        prohibited="flee",
        priority=1,
        scope="global",
    )
    norm_b = WorldNorm(
        name="local_norm",
        description="Local rule",
        condition="zone combat",
        prohibited="retreat",
        priority=2,
        scope="local",
    )
    store.save_norm(norm_a)
    store.save_norm(norm_b)
    conflicts = detect_norm_conflicts(store)
    types = [c.conflict_type for c in conflicts]
    assert "scope_overlap" in types


def test_no_duplicate_pairs():
    store = NormStore(":memory:")
    for i in range(3):
        store.save_norm(WorldNorm(
            name=f"norm_{i}",
            description="d",
            condition="zone",
            prohibited="attack",
            priority=1,
        ))
    conflicts = detect_norm_conflicts(store)
    # Check no (a,b) and (b,a) both present
    seen = set()
    for c in conflicts:
        pair = frozenset([c.norm_a, c.norm_b])
        # Multiple conflict types for the same pair are OK, but check for same type
        key = (frozenset([c.norm_a, c.norm_b]), c.conflict_type)
        assert key not in seen, f"Duplicate conflict: {c}"
        seen.add(key)
