"""normsync - World constitution engine for norm-governed multi-agent games."""

from __future__ import annotations

from importlib.metadata import version as _version

from normsync.closed_loop import (
    CRITICAL_REVIEW_SEVERITIES,
    DEFAULT_CROSS_SCOPE_ACTIONS,
    DEFAULT_RULE_REVIEW_DIMENSIONS,
    ClosedLoopError,
    GateOutcome,
    analyze_rule_review,
    assert_action_allowed,
    assert_in_scope,
    assert_rule_review_ok,
    gate_action,
    gate_actions,
    gate_rule_review,
    gate_scope,
    is_cross_scope_action,
    is_high_risk_action,
    is_rule_review_dimension,
)
from normsync.compliance import AgentCompliance, agent_compliance_report, fleet_compliance_report
from normsync.conflicts import NormConflict, detect_norm_conflicts
from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm
from normsync.report import print_violations, to_json, to_markdown
from normsync.store import NormStore
from normsync.versioning import NormVersion, NormVersionStore

__version__ = _version("normsync")
__all__ = [
    "CRITICAL_REVIEW_SEVERITIES",
    "DEFAULT_CROSS_SCOPE_ACTIONS",
    "DEFAULT_RULE_REVIEW_DIMENSIONS",
    "AgentAction",
    "AgentCompliance",
    "ClosedLoopError",
    "GateOutcome",
    "NormConflict",
    "NormMonitor",
    "NormRevision",
    "NormStore",
    "NormVersion",
    "NormVersionStore",
    "NormViolation",
    "WorldNorm",
    "agent_compliance_report",
    "analyze_rule_review",
    "assert_action_allowed",
    "assert_in_scope",
    "assert_rule_review_ok",
    "detect_norm_conflicts",
    "fleet_compliance_report",
    "gate_action",
    "gate_actions",
    "gate_rule_review",
    "gate_scope",
    "is_cross_scope_action",
    "is_high_risk_action",
    "is_rule_review_dimension",
    "print_violations",
    "to_json",
    "to_markdown",
]
