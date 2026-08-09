"""NORM-ENFORCE - unattended high-risk actions require active norms.

Farm: unattended post without governing norm.
Public: multi-agent coordination / ICLR failures - norms must constrain actions.
"""

from __future__ import annotations

import pytest

from normsync.closed_loop import (
    ClosedLoopError,
    assert_action_allowed,
    gate_action,
    gate_actions,
    is_high_risk_action,
)
from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm
from normsync.store import NormStore


def _post_norm() -> WorldNorm:
    """Norm that prohibits unattended auto_post (requires human context)."""
    return WorldNorm(
        name="no-unattended-post",
        description="Block auto_post without approval context",
        condition="unattended",
        prohibited="auto_post",
        scope="global",
        active=True,
        priority=10,
    )


def _safe_zone_norm() -> WorldNorm:
    return WorldNorm(
        name="no-attack-safe-zone",
        description="No attack in safe zones",
        condition="safe_zone",
        prohibited="attack",
        active=True,
    )


def test_post_is_high_risk() -> None:
    assert is_high_risk_action("post") is True
    assert is_high_risk_action("publish") is True
    assert is_high_risk_action("auto_post") is True
    assert is_high_risk_action("score") is False
    assert is_high_risk_action("") is True


def test_unattended_post_without_norms_fails_loud() -> None:
    """NORM-ENFORCE load-bearing fixture: post + empty norms → FAIL_LOUD."""
    out = gate_action("post", norms=[])
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.high_risk is True
    assert out.human_required is True
    assert out.active_norm_count == 0
    assert "NORM-ENFORCE" in out.reason
    assert "zero active norms" in out.reason.lower() or "without" in out.reason.lower()


def test_auto_post_without_norms_fails_loud() -> None:
    out = gate_action(AgentAction(agent_id="bot", action="auto_post", location="x"))
    assert out.verdict == "FAIL_LOUD"
    assert out.action == "auto_post"


def test_safe_action_without_norms_passes() -> None:
    out = gate_action("score", norms=[])
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.high_risk is False


def test_violation_fails() -> None:
    mon = NormMonitor([_safe_zone_norm()])
    act = AgentAction(agent_id="raider", action="attack", location="safe_zone_north")
    out = gate_action(act, mon)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.violation_count >= 1
    assert out.violations


def test_allowed_action_with_norms_passes() -> None:
    mon = NormMonitor([_safe_zone_norm()])
    act = AgentAction(agent_id="raider", action="move", location="safe_zone_north")
    out = gate_action(act, mon)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.active_norm_count == 1


def test_post_with_norms_no_violation_passes() -> None:
    """Having active norms satisfies high-risk presence; post not prohibited."""
    mon = NormMonitor([_safe_zone_norm()])
    out = gate_action("post", mon, agent_id="publisher", location="blog")
    assert out.ok is True
    assert out.high_risk is True
    assert out.active_norm_count == 1


def test_auto_post_unattended_violates_norm() -> None:
    mon = NormMonitor([_post_norm()])
    act = AgentAction(
        agent_id="cron",
        action="auto_post",
        location="unattended_lane",
    )
    out = gate_action(act, mon)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.violation_count >= 1


def test_assert_action_allowed_raises() -> None:
    with pytest.raises(ClosedLoopError, match=r"FAIL_LOUD|NORM-ENFORCE"):
        assert_action_allowed("publish", norms=[])


def test_assert_action_allowed_ok() -> None:
    mon = NormMonitor([_safe_zone_norm()])
    out = assert_action_allowed("post", mon)
    assert out.ok is True


def test_gate_actions_batch_first_failure() -> None:
    mon = NormMonitor([_safe_zone_norm()])
    actions = [
        AgentAction(agent_id="a", action="move", location="safe_zone"),
        AgentAction(agent_id="a", action="attack", location="safe_zone"),
    ]
    out = gate_actions(actions, mon)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_gate_actions_empty_fails_loud() -> None:
    out = gate_actions([], NormMonitor([_safe_zone_norm()]))
    assert out.verdict == "FAIL_LOUD"


def test_record_violations_to_store() -> None:
    store = NormStore(":memory:")
    mon = NormMonitor([_safe_zone_norm()])
    act = AgentAction(agent_id="x", action="attack", location="safe_zone")
    out = gate_action(act, mon, record_violations=True, store=store)
    assert out.ok is False
    saved = store.get_violations()
    assert len(saved) >= 1


def test_to_dict_serialisable() -> None:
    payload = gate_action("post", []).to_dict()
    assert payload["ok"] is False
    assert payload["verdict"] == "FAIL_LOUD"
    assert payload["high_risk"] is True


def test_prefixed_post_x_thread_high_risk() -> None:
    out = gate_action("post:x_thread", norms=[])
    assert out.verdict == "FAIL_LOUD"
    assert out.high_risk is True
