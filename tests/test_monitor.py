"""Tests for NormMonitor."""
from __future__ import annotations

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm


def make_safe_zone_norm() -> WorldNorm:
    return WorldNorm(
        name="no-attack-in-safe-zone",
        description="No attacking in safe zones",
        condition="safe_zone",
        prohibited="attack",
    )


def make_market_norm() -> WorldNorm:
    return WorldNorm(
        name="no-steal-in-market",
        description="No stealing in markets",
        condition="market",
        prohibited="steal",
    )


class TestNormMonitorBasics:
    def test_add_norm(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        assert len(monitor.active_norms()) == 1

    def test_active_norms_returns_only_active(self):
        monitor = NormMonitor()
        norm1 = make_safe_zone_norm()
        norm2 = make_market_norm()
        monitor.add_norm(norm1)
        monitor.add_norm(norm2)
        norm2.active = False
        assert len(monitor.active_norms()) == 1

    def test_repeal_norm_deactivates(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        rev = monitor.repeal_norm(norm.id)
        assert rev is not None
        assert rev.revision_type == "repeal"
        assert rev.norm_id == norm.id
        assert not norm.active

    def test_repeal_nonexistent_returns_none(self):
        monitor = NormMonitor()
        result = monitor.repeal_norm("nonexistent_id")
        assert result is None

    def test_repeal_already_inactive_returns_none(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        norm.active = False
        monitor.add_norm(norm)
        result = monitor.repeal_norm(norm.id)
        assert result is None

    def test_init_with_norms(self):
        norms = [make_safe_zone_norm(), make_market_norm()]
        monitor = NormMonitor(norms=norms)
        assert len(monitor.active_norms()) == 2


class TestNormMonitorCheck:
    def test_attack_in_safe_zone_is_violation(self):
        monitor = NormMonitor()
        monitor.add_norm(make_safe_zone_norm())
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert len(violations) == 1
        assert violations[0].norm_name == "no-attack-in-safe-zone"
        assert violations[0].agent_id == "agent1"

    def test_allowed_action_no_violation(self):
        monitor = NormMonitor()
        monitor.add_norm(make_safe_zone_norm())
        action = AgentAction("agent1", "trade", "safe_zone")
        violations = monitor.check(action)
        assert violations == []

    def test_attack_outside_safe_zone_no_violation(self):
        monitor = NormMonitor()
        monitor.add_norm(make_safe_zone_norm())
        action = AgentAction("agent1", "attack", "battle_zone")
        violations = monitor.check(action)
        assert violations == []

    def test_multiple_violations(self):
        monitor = NormMonitor()
        monitor.add_norm(make_safe_zone_norm())
        norm2 = WorldNorm("no-steal-in-safe-zone", "desc", "safe_zone", "steal")
        monitor.add_norm(norm2)
        action1 = AgentAction("agent1", "attack", "safe_zone")
        action2 = AgentAction("agent1", "steal", "safe_zone")
        v1 = monitor.check(action1)
        v2 = monitor.check(action2)
        assert len(v1) == 1
        assert len(v2) == 1

    def test_repealed_norm_not_triggered(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        monitor.repeal_norm(norm.id)
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert violations == []

    def test_empty_norms_no_violations(self):
        monitor = NormMonitor()
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert violations == []

    def test_condition_matching_case_insensitive(self):
        monitor = NormMonitor()
        norm = WorldNorm("test", "desc", "SAFE_ZONE", "ATTACK")
        monitor.add_norm(norm)
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert len(violations) == 1

    def test_violation_fields_are_correct(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        action = AgentAction("hero_agent", "attack", "safe_zone")
        violations = monitor.check(action)
        assert len(violations) == 1
        v = violations[0]
        assert v.agent_id == "hero_agent"
        assert v.norm_name == "no-attack-in-safe-zone"
        assert "hero_agent" in v.description
        assert "attack" in v.description
        assert "safe_zone" in v.description

    def test_steal_in_market_is_violation(self):
        monitor = NormMonitor()
        monitor.add_norm(make_market_norm())
        action = AgentAction("thief", "steal", "market")
        violations = monitor.check(action)
        assert len(violations) == 1

    def test_violation_id_is_16_hex(self):
        monitor = NormMonitor()
        monitor.add_norm(make_safe_zone_norm())
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert len(violations[0].id) == 16

    def test_no_violation_for_different_prohibited(self):
        monitor = NormMonitor()
        norm = WorldNorm("no-steal", "desc", "market", "steal")
        monitor.add_norm(norm)
        action = AgentAction("agent1", "trade", "market")
        violations = monitor.check(action)
        assert violations == []

    def test_violation_has_norm_id(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert violations[0].norm_id == norm.id

    def test_violation_has_action_id(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        action = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
        violations = monitor.check(action)
        assert violations[0].action_id == action.id

    def test_severity_is_warn_by_default(self):
        monitor = NormMonitor()
        norm = make_safe_zone_norm()
        monitor.add_norm(norm)
        action = AgentAction("agent1", "attack", "safe_zone")
        violations = monitor.check(action)
        assert violations[0].severity == "warn"
