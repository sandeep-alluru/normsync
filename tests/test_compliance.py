"""Tests for normsync.compliance."""
import pytest

from normsync.compliance import AgentCompliance, agent_compliance_report, fleet_compliance_report
from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm


def make_monitor():
    norm = WorldNorm(
        name="no_attack",
        description="No attacking in safe zones",
        condition="safe_zone",
        prohibited="attack",
    )
    return NormMonitor([norm])


def make_action(agent_id="agent-1", action="attack", location="safe_zone"):
    return AgentAction(agent_id=agent_id, action=action, location=location, timestamp=1.0)


def test_agent_compliance_no_violations():
    monitor = make_monitor()
    actions = [AgentAction(agent_id="a1", action="move", location="safe_zone", timestamp=1.0)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.agent_id == "a1"
    assert report.violations == 0
    assert report.compliance_rate == 1.0
    assert report.risk_level == "compliant"


def test_agent_compliance_with_violations():
    monitor = make_monitor()
    actions = [make_action("a1", "attack", "safe_zone") for _ in range(5)]
    actions += [AgentAction(agent_id="a1", action="move", location="safe_zone", timestamp=2.0)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.violations > 0
    assert report.compliance_rate < 1.0
    assert "no_attack" in report.violation_breakdown


def test_risk_level_non_compliant():
    monitor = make_monitor()
    # All actions are violations
    actions = [make_action("a1", "attack", "safe_zone") for _ in range(10)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.risk_level in ("non_compliant", "high_risk", "medium_risk")


def test_fleet_compliance_sorted():
    monitor = make_monitor()
    actions_by_agent = {
        "good_agent": [AgentAction(agent_id="good_agent", action="move", location="x", timestamp=1.0)],
        "bad_agent": [make_action("bad_agent", "attack", "safe_zone")],
    }
    reports = fleet_compliance_report(monitor, actions_by_agent)
    assert len(reports) == 2
    # Worst first (lowest compliance rate)
    assert reports[0].compliance_rate <= reports[1].compliance_rate


def test_trend_stable():
    monitor = NormMonitor([])  # no norms = no violations
    actions = [AgentAction(agent_id="a1", action="move", location="x", timestamp=float(i)) for i in range(10)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.trend == "stable"


def test_risk_level_low_risk():
    """compliance_rate >= 0.9 but < 1.0 -> low_risk."""
    monitor = make_monitor()
    # 1 violation out of 10 actions = 0.9 rate
    actions = [AgentAction(agent_id="a1", action="move", location="safe_zone", timestamp=float(i))
               for i in range(9)]
    actions.append(make_action("a1", "attack", "safe_zone"))
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.risk_level == "low_risk"


def test_risk_level_medium_risk():
    """compliance_rate >= 0.7 but < 0.9 -> medium_risk."""
    monitor = make_monitor()
    # 2 violations out of 10 actions = 0.8 rate
    actions = [AgentAction(agent_id="a1", action="move", location="safe_zone", timestamp=float(i))
               for i in range(8)]
    actions += [make_action("a1", "attack", "safe_zone") for _ in range(2)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.risk_level == "medium_risk"


def test_risk_level_high_risk():
    """compliance_rate >= 0.5 but < 0.7 -> high_risk."""
    monitor = make_monitor()
    # 4 violations out of 10 actions = 0.6 rate
    actions = [AgentAction(agent_id="a1", action="move", location="safe_zone", timestamp=float(i))
               for i in range(6)]
    actions += [make_action("a1", "attack", "safe_zone") for _ in range(4)]
    report = agent_compliance_report(monitor, "a1", actions)
    assert report.risk_level == "high_risk"
