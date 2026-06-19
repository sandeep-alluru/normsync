"""normsync — World constitution engine for norm-governed multi-agent games."""

from __future__ import annotations

from importlib.metadata import version as _version

from normsync.compliance import AgentCompliance, agent_compliance_report, fleet_compliance_report
from normsync.conflicts import NormConflict, detect_norm_conflicts
from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm
from normsync.report import print_violations, to_json, to_markdown
from normsync.store import NormStore
from normsync.versioning import NormVersion, NormVersionStore

__version__ = _version("normsync")
__all__ = [
    "AgentAction",
    "AgentCompliance",
    "NormConflict",
    "NormMonitor",
    "NormRevision",
    "NormStore",
    "NormVersion",
    "NormVersionStore",
    "NormViolation",
    "WorldNorm",
    "agent_compliance_report",
    "detect_norm_conflicts",
    "fleet_compliance_report",
    "print_violations",
    "to_json",
    "to_markdown",
]
