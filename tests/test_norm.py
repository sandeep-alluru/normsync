"""Tests for WorldNorm, AgentAction, NormViolation, NormRevision data models."""
from __future__ import annotations

from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm


class TestWorldNorm:
    def test_id_is_16_chars_hex(self):
        norm = WorldNorm("test", "desc", "location == safe", "action == attack")
        assert len(norm.id) == 16
        assert all(c in "0123456789abcdef" for c in norm.id)

    def test_same_inputs_same_id(self):
        n1 = WorldNorm("no-attack", "desc", "safe_zone", "attack")
        n2 = WorldNorm("no-attack", "desc2", "safe_zone", "attack")
        assert n1.id == n2.id  # id based on name|condition|prohibited

    def test_different_inputs_different_id(self):
        n1 = WorldNorm("no-attack", "desc", "safe_zone", "attack")
        n2 = WorldNorm("no-steal", "desc", "market", "steal")
        assert n1.id != n2.id

    def test_to_dict_has_all_fields(self):
        norm = WorldNorm("test", "a test", "cond", "prohibited")
        d = norm.to_dict()
        assert set(d.keys()) == {
            "id",
            "name",
            "description",
            "condition",
            "prohibited",
            "scope",
            "active",
            "priority",
        }

    def test_to_dict_values(self):
        norm = WorldNorm(
            "no-attack", "No attacking", "safe_zone", "attack", scope="local", priority=5
        )
        d = norm.to_dict()
        assert d["name"] == "no-attack"
        assert d["scope"] == "local"
        assert d["priority"] == 5
        assert d["active"] is True

    def test_from_dict_restores_fields(self):
        original = WorldNorm(
            "no-attack", "desc", "safe_zone", "attack", scope="regional", priority=2
        )
        d = original.to_dict()
        restored = WorldNorm.from_dict(d)
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.condition == original.condition
        assert restored.prohibited == original.prohibited
        assert restored.scope == original.scope
        assert restored.priority == original.priority

    def test_from_dict_defaults(self):
        d = {"name": "n", "description": "d", "condition": "c", "prohibited": "p"}
        norm = WorldNorm.from_dict(d)
        assert norm.scope == "global"
        assert norm.active is True
        assert norm.priority == 0

    def test_default_scope_global(self):
        norm = WorldNorm("n", "d", "c", "p")
        assert norm.scope == "global"

    def test_default_active_true(self):
        norm = WorldNorm("n", "d", "c", "p")
        assert norm.active is True

    def test_default_priority_zero(self):
        norm = WorldNorm("n", "d", "c", "p")
        assert norm.priority == 0

    def test_id_is_content_addressed_on_name_condition_prohibited(self):
        n1 = WorldNorm("same-name", "different description", "same_cond", "same_prohibited")
        n2 = WorldNorm("same-name", "very different", "same_cond", "same_prohibited")
        assert n1.id == n2.id

    def test_id_changes_with_condition(self):
        n1 = WorldNorm("no-attack", "desc", "safe_zone", "attack")
        n2 = WorldNorm("no-attack", "desc", "danger_zone", "attack")
        assert n1.id != n2.id

    def test_id_changes_with_prohibited(self):
        n1 = WorldNorm("no-attack", "desc", "zone", "attack")
        n2 = WorldNorm("no-attack", "desc", "zone", "steal")
        assert n1.id != n2.id


class TestAgentAction:
    def test_id_is_16_chars_hex(self):
        act = AgentAction("agent1", "attack", "safe_zone")
        assert len(act.id) == 16
        assert all(c in "0123456789abcdef" for c in act.id)

    def test_id_content_addressed(self):
        a1 = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
        a2 = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
        assert a1.id == a2.id

    def test_different_timestamp_different_id(self):
        a1 = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
        a2 = AgentAction("agent1", "attack", "safe_zone", timestamp=2.0)
        assert a1.id != a2.id

    def test_to_dict_fields(self):
        act = AgentAction("agent1", "attack", "safe_zone", target="enemy", faction="red")
        d = act.to_dict()
        assert d["agent_id"] == "agent1"
        assert d["action"] == "attack"
        assert d["location"] == "safe_zone"
        assert d["target"] == "enemy"
        assert d["faction"] == "red"


class TestNormViolation:
    def test_id_is_16_chars_hex(self):
        v = NormViolation("norm1", "no-attack", "act1", "agent1", "desc")
        assert len(v.id) == 16

    def test_id_content_addressed(self):
        v1 = NormViolation("norm1", "no-attack", "act1", "agent1", "desc")
        v2 = NormViolation("norm1", "no-attack", "act1", "agent2", "different")
        assert v1.id == v2.id  # id based on norm_id|action_id only

    def test_to_dict_fields(self):
        v = NormViolation(
            "norm1", "no-attack", "act1", "agent1", "desc", severity="error", timestamp=1.0
        )
        d = v.to_dict()
        assert d["norm_id"] == "norm1"
        assert d["agent_id"] == "agent1"
        assert d["severity"] == "error"
        assert d["timestamp"] == 1.0

    def test_default_severity_warn(self):
        v = NormViolation("n", "name", "a", "agent", "desc")
        assert v.severity == "warn"


class TestNormRevision:
    def test_id_is_16_chars_hex(self):
        rev = NormRevision("norm1", "create")
        assert len(rev.id) == 16

    def test_id_content_addressed(self):
        rev1 = NormRevision("norm1", "repeal", timestamp=1.0)
        rev2 = NormRevision("norm1", "repeal", timestamp=1.0)
        assert rev1.id == rev2.id

    def test_to_dict_fields(self):
        rev = NormRevision("norm1", "create", reason="initial", timestamp=1.0)
        d = rev.to_dict()
        assert d["norm_id"] == "norm1"
        assert d["revision_type"] == "create"
        assert d["reason"] == "initial"
