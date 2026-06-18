"""NormMonitor: check agent actions against active norms."""
from __future__ import annotations

import time

from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm


class NormMonitor:
    """Check agent actions against active norms using simple string matching."""

    def __init__(self, norms: list[WorldNorm] | None = None) -> None:
        self._norms: list[WorldNorm] = list(norms or [])

    def add_norm(self, norm: WorldNorm) -> None:
        """Add a norm to the monitor."""
        self._norms.append(norm)

    def repeal_norm(self, norm_id: str) -> NormRevision | None:
        """Deactivate a norm by ID and return a NormRevision record."""
        for norm in self._norms:
            if norm.id == norm_id and norm.active:
                norm.active = False
                return NormRevision(
                    norm_id=norm_id,
                    revision_type="repeal",
                    timestamp=time.time(),
                )
        return None

    def active_norms(self) -> list[WorldNorm]:
        """Return all currently active norms."""
        return [n for n in self._norms if n.active]

    def check(self, action: AgentAction) -> list[NormViolation]:
        """Check action against all active norms.

        Matching: condition tokens appear in action fields AND prohibited matches action.action.
        Example: norm condition "safe_zone", prohibited "attack"
        -> if action.location contains "safe_zone" and action.action == "attack" -> violation
        """
        violations = []
        action_fields = " ".join(
            [action.action, action.location, action.target, action.faction]
        ).lower()

        for norm in self.active_norms():
            condition_tokens = norm.condition.lower().replace("==", "").split()
            condition_matches = all(tok in action_fields for tok in condition_tokens)

            prohibited_tokens = norm.prohibited.lower().replace("==", "").split()
            action_word = action.action.lower().strip()
            prohibited_match = any(
                tok == action_word or tok in action_word for tok in prohibited_tokens
            )

            if condition_matches and prohibited_match:
                v = NormViolation(
                    norm_id=norm.id,
                    norm_name=norm.name,
                    action_id=action.id,
                    agent_id=action.agent_id,
                    description=(
                        f"Agent '{action.agent_id}' performed '{action.action}' "
                        f"in '{action.location}', violating norm '{norm.name}'"
                    ),
                    severity="warn",
                    timestamp=action.timestamp or time.time(),
                )
                violations.append(v)

        return violations
