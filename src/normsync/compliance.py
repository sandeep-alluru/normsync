"""Agent compliance scoring."""
from __future__ import annotations

from dataclasses import dataclass

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction


@dataclass
class AgentCompliance:
    agent_id: str
    total_actions: int
    violations: int
    compliance_rate: float          # 0-1
    violation_breakdown: dict[str, int]  # norm_name -> violation count
    # "compliant", "low_risk", "medium_risk", "high_risk", "non_compliant"
    risk_level: str
    trend: str                      # "improving", "stable", "degrading"


def _risk_level(compliance_rate: float) -> str:
    if compliance_rate == 1.0:
        return "compliant"
    if compliance_rate >= 0.9:
        return "low_risk"
    if compliance_rate >= 0.7:
        return "medium_risk"
    if compliance_rate >= 0.5:
        return "high_risk"
    return "non_compliant"


def _violation_rate(actions: list[AgentAction], monitor: NormMonitor) -> float:
    """Fraction of actions that produced at least one violation."""
    if not actions:
        return 0.0
    violating = sum(1 for a in actions if monitor.check(a))
    return violating / len(actions)


def agent_compliance_report(
    monitor: NormMonitor,
    agent_id: str,
    actions: list[AgentAction],
) -> AgentCompliance:
    """Compute compliance report for a single agent."""
    # Filter to only actions for this agent
    agent_actions = [a for a in actions if a.agent_id == agent_id]
    total_actions = len(agent_actions)

    # Check each action and collect violations
    all_violations = []
    violating_action_count = 0
    for action in agent_actions:
        viols = monitor.check(action)
        if viols:
            violating_action_count += 1
        all_violations.extend(viols)

    total_violations = len(all_violations)

    # Build violation breakdown by norm name
    violation_breakdown: dict[str, int] = {}
    for v in all_violations:
        violation_breakdown[v.norm_name] = violation_breakdown.get(v.norm_name, 0) + 1

    # Compliance rate: fraction of actions with ZERO violations (always 0-1)
    compliance_rate = 1.0 - (violating_action_count / max(1, total_actions))

    # Risk level
    risk = _risk_level(compliance_rate)

    # Trend: split actions in half, compare violation rates
    mid = len(agent_actions) // 2
    first_half = agent_actions[:mid]
    second_half = agent_actions[mid:]
    first_rate = _violation_rate(first_half, monitor)
    second_rate = _violation_rate(second_half, monitor)

    if second_rate < first_rate - 0.1:
        trend = "improving"
    elif second_rate > first_rate + 0.1:
        trend = "degrading"
    else:
        trend = "stable"

    return AgentCompliance(
        agent_id=agent_id,
        total_actions=total_actions,
        violations=total_violations,
        compliance_rate=compliance_rate,
        violation_breakdown=violation_breakdown,
        risk_level=risk,
        trend=trend,
    )


def fleet_compliance_report(
    monitor: NormMonitor,
    actions_by_agent: dict[str, list[AgentAction]],
) -> list[AgentCompliance]:
    """Report compliance for a whole fleet of agents.

    Sorted worst first (by compliance_rate ascending).
    """
    reports = [
        agent_compliance_report(monitor, agent_id, agent_actions)
        for agent_id, agent_actions in actions_by_agent.items()
    ]
    reports.sort(key=lambda r: r.compliance_rate)
    return reports
