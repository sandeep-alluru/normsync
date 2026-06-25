"""NormMonitor: check agent actions against active norms."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm

if TYPE_CHECKING:
    from normsync.store import NormStore


class NormMonitor:
    """Check agent actions against active norms using simple string matching.

    Can be constructed with either a list of WorldNorm objects or a NormStore.
    When constructed with a NormStore, norms are read from the store on every
    call to ``active_norms()`` and ``check()``, so policy changes propagate to
    all monitors sharing the same store without any restart.

    Examples::

        # In-memory list of norms (norm list is fixed after construction)
        monitor = NormMonitor(norms=[...])

        # Live NormStore — picks up norm changes automatically
        monitor = NormMonitor(store)
    """

    def __init__(
        self,
        norms: list[WorldNorm] | NormStore | None = None,
        *,
        store: NormStore | None = None,
    ) -> None:
        # Support both NormMonitor(store) and NormMonitor(store=store)
        from normsync.store import NormStore as _NormStore  # local to avoid circular at module level

        if isinstance(norms, _NormStore):
            self._store: NormStore | None = norms
            self._norms: list[WorldNorm] = []
        else:
            self._store = store
            self._norms = list(norms or [])

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
        """Return all currently active norms.

        When the monitor was constructed with a ``NormStore``, this queries
        the store live so that any norm changes are immediately reflected.
        """
        if self._store is not None:
            return self._store.get_norms(active_only=True)
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
