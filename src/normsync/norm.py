"""Core data model for normsync."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldNorm:
    """A normative rule governing agent behavior."""

    name: str
    description: str
    condition: str
    prohibited: str
    scope: str = "global"
    active: bool = True
    priority: int = 0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = f"{self.name}|{self.condition}|{self.prohibited}"
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "condition": self.condition,
            "prohibited": self.prohibited,
            "scope": self.scope,
            "active": self.active,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldNorm:
        n = cls(
            name=d["name"],
            description=d["description"],
            condition=d["condition"],
            prohibited=d["prohibited"],
            scope=d.get("scope", "global"),
            active=d.get("active", True),
            priority=d.get("priority", 0),
        )
        return n


@dataclass
class AgentAction:
    """An action taken by an agent."""

    agent_id: str
    action: str
    location: str = ""
    target: str = ""
    faction: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = f"{self.agent_id}|{self.action}|{self.location}|{self.timestamp}"
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "action": self.action,
            "location": self.location,
            "target": self.target,
            "faction": self.faction,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class NormViolation:
    """Emitted when an agent action violates a norm."""

    norm_id: str
    norm_name: str
    action_id: str
    agent_id: str
    description: str
    severity: str = "warn"
    timestamp: float = 0.0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = f"{self.norm_id}|{self.action_id}|{self.timestamp}"
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "norm_id": self.norm_id,
            "norm_name": self.norm_name,
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "description": self.description,
            "severity": self.severity,
            "timestamp": self.timestamp,
        }


@dataclass
class NormRevision:
    """Records when a norm is created, modified, or repealed."""

    norm_id: str
    revision_type: str
    reason: str = ""
    timestamp: float = 0.0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = f"{self.norm_id}|{self.revision_type}|{self.timestamp}"
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "norm_id": self.norm_id,
            "revision_type": self.revision_type,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }
