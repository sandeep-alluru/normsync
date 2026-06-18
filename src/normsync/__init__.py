"""normsync — World constitution engine for norm-governed multi-agent games."""
from __future__ import annotations

from importlib.metadata import version as _version

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm
from normsync.report import print_violations, to_json, to_markdown
from normsync.store import NormStore

__version__ = _version("normsync")
__all__ = [
    "AgentAction",
    "NormMonitor",
    "NormRevision",
    "NormStore",
    "NormViolation",
    "WorldNorm",
    "print_violations",
    "to_json",
    "to_markdown",
]
