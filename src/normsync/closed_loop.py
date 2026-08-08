"""Closed-loop action gate for normsync (NORM-ENFORCE + SCOPE-BOUND / MNC).

Who reads the output?
  Agent runtimes, publish loops, CI — anything that must *block* an action
  when norms forbid it or when the norm registry is empty (write-only ornament);
  multi-agent channels that must refuse out-of-scope declassification/export.

What outcome changes?
  High-risk unattended actions (e.g. ``post``) without active norms → FAIL_LOUD.
  Actions that violate active norms → FAIL.
  Allowed actions with a live norm set → PASS.
  Export/share targets outside declared scope → FAIL (MNC SCOPE-BOUND).
  Empty declared scope → FAIL_LOUD.

Farm case NORM-ENFORCE:
  Unattended post without a governing norm. A norm store that is never checked
  is ornament. The gate is the load-bearing reader.

Public map:
  * multi-agent coordination / ICLR multi-agent failures / SocietyBench
  * MNC scope-bound semantic declassification (arXiv 2608.01719) — private
    agent communication must not leak outside declared scope
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
        "declassify",
        "export",
        "share",
        "broadcast",
        "reveal",
    }
)

# Actions that move content across scope boundaries (MNC declassification class).
DEFAULT_CROSS_SCOPE_ACTIONS: frozenset[str] = frozenset(
    {
        "export",
        "share",
        "publish",
        "post",
        "broadcast",
        "send",
        "send_email",
        "declassify",
        "reveal",
        "exfiltrate",
        "forward",
        "cc_external",
    }
)

# Classification ranks — higher is more public.
_CLASS_RANK: dict[str, int] = {
    "secret": 0,
    "private": 1,
    "internal": 2,
    "team": 2,
    "confidential": 1,
    "restricted": 1,
    "public": 3,
    "open": 3,
}


class ClosedLoopError(ValueError):
    """Raised when an action is refused by the norm gate."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of gating an agent action against norms or scope bounds.

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
        declared_scope: Scope labels when scope-gated.
        target_scope: Target scope labels when scope-gated.
        out_of_scope: Targets outside declared scope.
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
    declared_scope: tuple[str, ...] = ()
    target_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()

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
            "declared_scope": list(self.declared_scope),
            "target_scope": list(self.target_scope),
            "out_of_scope": list(self.out_of_scope),
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


# ---------------------------------------------------------------------------
# SCOPE-BOUND / MNC — refuse out-of-scope declassification & export
# ---------------------------------------------------------------------------


def _canon_scope(label: str) -> str:
    return (label or "").strip().lower().replace(" ", "_").replace("-", "_")


def _scope_set(labels: Sequence[str] | str | None) -> list[str]:
    if labels is None:
        return []
    if isinstance(labels, str):
        labels = [labels]
    out: list[str] = []
    seen: set[str] = set()
    for x in labels:
        s = _canon_scope(str(x))
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def is_cross_scope_action(action: str) -> bool:
    """True if *action* can move content across communication scopes."""
    a = _canonical_action(action)
    if not a:
        return False
    head = a.split(":", 1)[0]
    return a in DEFAULT_CROSS_SCOPE_ACTIONS or head in DEFAULT_CROSS_SCOPE_ACTIONS


def gate_scope(
    action: str,
    *,
    declared_scope: Sequence[str] | str | None = None,
    target_scope: Sequence[str] | str | None = None,
    classification: str = "private",
    allow_declassify: bool = False,
    require_declared_scope: bool = True,
) -> GateOutcome:
    """Refuse out-of-scope export/declassify (MNC SCOPE-BOUND class).

    Public case: arXiv 2608.01719 *MNC: Scope-Bound Semantic Declassification
    for Private LLM-Agent Communication*. Multi-agent channels declare a
    communication scope; agents must not share/export/declassify content to
    audiences outside that scope without an explicit declassify grant.

    Rules:

    1. Empty action → **FAIL_LOUD**
    2. Empty ``declared_scope`` when required → **FAIL_LOUD**
    3. Any ``target_scope`` not ⊆ ``declared_scope`` → **FAIL** (scope escape)
    4. Cross-scope action (export/share/publish/…) on private/secret content
       toward a more public classification without ``allow_declassify`` → **FAIL**
    5. In-scope, no unauthorized declassify → **PASS**

    Args:
        action: Proposed action (e.g. ``share``, ``export``, ``send``).
        declared_scope: Allowed audience/scope labels for this channel.
        target_scope: Scope(s) the action would reach (recipients, channels).
        classification: Content classification (private/internal/public/…).
        allow_declassify: Human/policy grant to widen classification.
        require_declared_scope: Empty declared scope → FAIL_LOUD.
    """
    canon = _canonical_action(action)
    declared = _scope_set(declared_scope)
    targets = _scope_set(target_scope)
    klass = _canon_scope(classification) or "private"

    if not canon:
        return _fail_loud(
            "SCOPE-BOUND/MNC: empty action — cannot gate phantom declassify",
            action=None,
            high_risk=True,
            declared_scope=tuple(declared),
            target_scope=tuple(targets),
        )

    if require_declared_scope and len(declared) == 0:
        return _fail_loud(
            "SCOPE-BOUND/MNC: empty declared_scope — private agent channel "
            "has no bound; cannot authorize share/export (arXiv 2608.01719)",
            action=canon,
            high_risk=True,
            declared_scope=(),
            target_scope=tuple(targets),
        )

    declared_set = set(declared)
    oos = [t for t in targets if t not in declared_set]
    if oos:
        return _fail(
            f"SCOPE-BOUND/MNC: target_scope {oos} outside declared_scope "
            f"{declared} for action {canon!r} — refuse scope escape / leak",
            action=canon,
            high_risk=True,
            declared_scope=tuple(declared),
            target_scope=tuple(targets),
            out_of_scope=tuple(oos),
            violation_count=len(oos),
        )

    # Declassification: cross-scope action with private content → public-ish
    # without allow_declassify.
    if is_cross_scope_action(canon) and not allow_declassify:
        src_rank = _CLASS_RANK.get(klass, 1)
        # If any target looks public/external, treat as widen
        public_targets = {
            t
            for t in targets
            if t in {"public", "open", "external", "internet", "www"}
            or t.startswith("public_")
            or t.startswith("ext_")
        }
        # Also: classification public without grant when action is declassify
        if canon in {"declassify", "reveal", "exfiltrate"} and src_rank < 3:
            return _fail(
                f"SCOPE-BOUND/MNC: {canon!r} of classification={klass!r} "
                f"without allow_declassify — refuse unauthorized declassification",
                action=canon,
                high_risk=True,
                declared_scope=tuple(declared),
                target_scope=tuple(targets),
            )
        if public_targets and src_rank < 3:
            return _fail(
                f"SCOPE-BOUND/MNC: {canon!r} moves {klass!r} content to "
                f"public targets {sorted(public_targets)} without "
                f"allow_declassify — refuse scope-bound leak",
                action=canon,
                high_risk=True,
                declared_scope=tuple(declared),
                target_scope=tuple(targets),
                out_of_scope=tuple(sorted(public_targets)),
            )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"SCOPE-BOUND ok: action={canon!r} class={klass!r} "
            f"declared={declared} targets={targets} "
            f"allow_declassify={allow_declassify}"
        ),
        exit_code=0,
        action=canon,
        human_required=False,
        high_risk=is_cross_scope_action(canon),
        declared_scope=tuple(declared),
        target_scope=tuple(targets),
        out_of_scope=(),
    )


def assert_in_scope(
    action: str,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_scope` is ok."""
    outcome = gate_scope(action, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
