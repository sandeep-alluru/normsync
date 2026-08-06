"""Closed-loop action gate for normsync (NORM-ENFORCE / Non-Ornament L7).

Who reads the output?
  Agent runtimes, publish loops, CI — anything that must *block* an action
  when norms forbid it or when the norm registry is empty (write-only ornament).

What outcome changes?
  High-risk unattended actions (e.g. ``post``) without active norms → FAIL_LOUD.
  Actions that violate active norms → FAIL.
  Allowed actions with a live norm set → PASS.

Farm case NORM-ENFORCE:
  Unattended post without a governing norm. A norm store that is never checked
  is ornament. The gate is the load-bearing reader.

Public map: multi-agent coordination / ICLR multi-agent failures / SocietyBench —
shared norms must constrain actions, not only be stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormViolation, WorldNorm

# Actions that require at least one active governing norm (unattended risk).
DEFAULT_HIGH_RISK_ACTIONS: frozenset[str] = frozenset(
    {
        "post",
        "publish",
        "auto_post",
        "tweet",
        "send",
        "send_email",
        "delete",
        "wipe",
        "deploy",
        "transfer",
        "attack",
        "exfiltrate",
    }
)


class ClosedLoopError(ValueError):
    """Raised when an action is refused by the norm gate."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of gating an agent action against norms.

    Attributes:
        ok: True only when the action may proceed.
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Always non-empty.
        exit_code: 0 PASS, 1 FAIL (violation), 2 FAIL_LOUD (no norms / empty).
        action: Canonical action string.
        agent_id: Acting agent when known.
        active_norm_count: Active norms considered.
        violation_count: Violations found.
        violations: Structured violation payloads.
        human_required: True when enforcement needs human review.
        high_risk: Whether the action was classified high-risk.
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    action: str | None = None
    agent_id: str | None = None
    active_norm_count: int = 0
    violation_count: int = 0
    violations: tuple[dict[str, Any], ...] = ()
    human_required: bool = False
    high_risk: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "action": self.action,
            "agent_id": self.agent_id,
            "active_norm_count": self.active_norm_count,
            "violation_count": self.violation_count,
            "violations": list(self.violations),
            "human_required": self.human_required,
            "high_risk": self.high_risk,
        }


def _canonical_action(action: str) -> str:
    return (action or "").strip().lower().replace(" ", "_")


def is_high_risk_action(
    action: str,
    *,
    extra: Iterable[str] | None = None,
) -> bool:
    """True if *action* requires active norms before unattended execution."""
    a = _canonical_action(action)
    if not a:
        return True
    banned = set(DEFAULT_HIGH_RISK_ACTIONS)
    if extra:
        banned |= {_canonical_action(x) for x in extra}
    if a in banned:
        return True
    head = a.split(":", 1)[0]
    return head in banned


def _fail_loud(reason: str, **kwargs: Any) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        human_required=True,
        **kwargs,
    )


def _fail(reason: str, **kwargs: Any) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        human_required=True,
        **kwargs,
    )


def _as_monitor(
    norms: NormMonitor | Sequence[WorldNorm] | None,
) -> NormMonitor:
    if isinstance(norms, NormMonitor):
        return norms
    return NormMonitor(list(norms or []))


def gate_action(
    action: AgentAction | str,
    norms: NormMonitor | Sequence[WorldNorm] | None = None,
    *,
    agent_id: str = "agent",
    location: str = "",
    target: str = "",
    faction: str = "",
    require_norms_for_high_risk: bool = True,
    extra_high_risk: Iterable[str] | None = None,
    record_violations: bool = False,
    store: Any = None,
) -> GateOutcome:
    """Gate an agent action: enforce norms; refuse unattended high-risk without norms.

    Args:
        action: :class:`AgentAction` or action name string (e.g. ``\"post\"``).
        norms: :class:`NormMonitor` or sequence of :class:`WorldNorm`.
        agent_id / location / target / faction: Used when *action* is a string.
        require_norms_for_high_risk: If True (default), high-risk actions with
            zero active norms → FAIL_LOUD (NORM-ENFORCE / unattended post).
        extra_high_risk: Additional action names treated as high-risk.
        record_violations: If True and *store* has ``save_violation``, persist.
        store: Optional NormStore for recording violations.

    Returns:
        :class:`GateOutcome` — callers should refuse the side effect unless ``ok``.
    """
    if isinstance(action, AgentAction):
        act = action
    else:
        act = AgentAction(
            agent_id=agent_id,
            action=str(action),
            location=location,
            target=target,
            faction=faction,
        )

    canon = _canonical_action(act.action)
    high_risk = is_high_risk_action(canon, extra=extra_high_risk)
    monitor = _as_monitor(norms)
    active = monitor.active_norms()
    n_active = len(active)

    if not canon:
        return _fail_loud(
            "empty action — refuse (NORM-ENFORCE)",
            action="",
            agent_id=act.agent_id,
            active_norm_count=n_active,
            high_risk=True,
        )

    # NORM-ENFORCE: unattended high-risk with no live norms is ornament failure
    if require_norms_for_high_risk and high_risk and n_active == 0:
        return _fail_loud(
            f"NORM-ENFORCE: high-risk action {canon!r} with zero active norms — "
            f"unattended post/publish without governing norm (write-only registry)",
            action=canon,
            agent_id=act.agent_id,
            active_norm_count=0,
            high_risk=True,
        )

    violations: list[NormViolation] = monitor.check(act)
    if record_violations and store is not None and hasattr(store, "save_violation"):
        for v in violations:
            store.save_violation(v)

    v_payloads = tuple(v.to_dict() for v in violations)

    if violations:
        names = sorted({v.norm_name for v in violations})
        return _fail(
            f"NORM-ENFORCE: action {canon!r} violates {len(violations)} norm(s): "
            f"{names}",
            action=canon,
            agent_id=act.agent_id,
            active_norm_count=n_active,
            violation_count=len(violations),
            violations=v_payloads,
            high_risk=high_risk,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"action {canon!r} allowed under {n_active} active norm(s)"
            if n_active
            else f"action {canon!r} allowed (non-high-risk; no norms required)"
        ),
        exit_code=0,
        action=canon,
        agent_id=act.agent_id,
        active_norm_count=n_active,
        violation_count=0,
        violations=(),
        human_required=False,
        high_risk=high_risk,
    )


def assert_action_allowed(
    action: AgentAction | str,
    norms: NormMonitor | Sequence[WorldNorm] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Gate action and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_action(action, norms, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


def gate_actions(
    actions: Sequence[AgentAction],
    norms: NormMonitor | Sequence[WorldNorm] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Gate a batch; first failure wins (FAIL/FAIL_LOUD). All PASS → PASS."""
    if not actions:
        return _fail_loud("empty action batch — nothing to enforce")

    last_ok: GateOutcome | None = None
    for act in actions:
        out = gate_action(act, norms, **kwargs)
        if not out.ok:
            return out
        last_ok = out
    assert last_ok is not None
    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=f"batch ok: {len(actions)} actions under norms",
        exit_code=0,
        action=last_ok.action,
        agent_id=last_ok.agent_id,
        active_norm_count=last_ok.active_norm_count,
        high_risk=False,
    )
