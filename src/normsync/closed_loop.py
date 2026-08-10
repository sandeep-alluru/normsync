"""Closed-loop action gate for normsync (NORM-ENFORCE + SCOPE-BOUND + RULE-INTENSIVE).

Who reads the output?
  Agent runtimes, publish loops, CI - anything that must *block* an action
  when norms forbid it or when the norm registry is empty (write-only ornament);
  multi-agent channels that must refuse out-of-scope declassification/export;
  rule-intensive document reviewers that must refuse approve without taxonomy coverage.

What outcome changes?
  High-risk unattended actions (e.g. ``post``) without active norms → FAIL_LOUD.
  Actions that violate active norms → FAIL.
  Allowed actions with a live norm set → PASS.
  Export/share targets outside declared scope → FAIL (MNC SCOPE-BOUND).
  Empty declared scope → FAIL_LOUD.
  Document review "approved" without hierarchical taxonomy coverage → FAIL_LOUD/FAIL
  (RULE-INTENSIVE / GB/T-Bench class).

Farm case NORM-ENFORCE:
  Unattended post without a governing norm. A norm store that is never checked
  is ornament. The gate is the load-bearing reader.

Public map:
  * multi-agent coordination / ICLR multi-agent failures / SocietyBench
  * MNC scope-bound semantic declassification (arXiv 2608.01719) - private
    agent communication must not leak outside declared scope
  * Rule-intensive national-standard review (arXiv 2608.06312 GB/T-Bench) -
    hierarchical schema: structure, scope, normative modality, terminology,
    cross-section consistency
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

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

# Classification ranks - higher is more public.
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
    """Result of gating an agent action against norms, scope, or rule-review.

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
        covered_dimensions: Rule-review taxonomy dimensions covered.
        missing_dimensions: Required taxonomy dimensions not covered.
        critical_finding_count: Unresolved critical review findings.
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
    covered_dimensions: tuple[str, ...] = ()
    missing_dimensions: tuple[str, ...] = ()
    critical_finding_count: int = 0

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
            "covered_dimensions": list(self.covered_dimensions),
            "missing_dimensions": list(self.missing_dimensions),
            "critical_finding_count": self.critical_finding_count,
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
        :class:`GateOutcome` - callers should refuse the side effect unless ``ok``.
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
            "empty action - refuse (NORM-ENFORCE)",
            action="",
            agent_id=act.agent_id,
            active_norm_count=n_active,
            high_risk=True,
        )

    # NORM-ENFORCE: unattended high-risk with no live norms is ornament failure
    if require_norms_for_high_risk and high_risk and n_active == 0:
        return _fail_loud(
            f"NORM-ENFORCE: high-risk action {canon!r} with zero active norms - "
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
            f"NORM-ENFORCE: action {canon!r} violates {len(violations)} norm(s): {names}",
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
        return _fail_loud("empty action batch - nothing to enforce")

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
# SCOPE-BOUND / MNC - refuse out-of-scope declassification & export
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
            "SCOPE-BOUND/MNC: empty action - cannot gate phantom declassify",
            action=None,
            high_risk=True,
            declared_scope=tuple(declared),
            target_scope=tuple(targets),
        )

    if require_declared_scope and len(declared) == 0:
        return _fail_loud(
            "SCOPE-BOUND/MNC: empty declared_scope - private agent channel "
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
            f"{declared} for action {canon!r} - refuse scope escape / leak",
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
                f"without allow_declassify - refuse unauthorized declassification",
                action=canon,
                high_risk=True,
                declared_scope=tuple(declared),
                target_scope=tuple(targets),
            )
        if public_targets and src_rank < 3:
            return _fail(
                f"SCOPE-BOUND/MNC: {canon!r} moves {klass!r} content to "
                f"public targets {sorted(public_targets)} without "
                f"allow_declassify - refuse scope-bound leak",
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


# ---------------------------------------------------------------------------
# RULE-INTENSIVE / GB/T-Bench - hierarchical document review taxonomy
# Public: arXiv 2608.06312 Benchmarking LLMs for Rule-Intensive Review
# ---------------------------------------------------------------------------

# GB/T Review Taxonomy (hierarchical schema from the paper).
DEFAULT_RULE_REVIEW_DIMENSIONS: frozenset[str] = frozenset(
    {
        "document_structure",
        "scope_alignment",
        "normative_modality",
        "terminology_consistency",
        "cross_section_consistency",
    }
)

# Severities that block approve when unresolved.
CRITICAL_REVIEW_SEVERITIES: frozenset[str] = frozenset(
    {
        "critical",
        "blocker",
        "error",
        "high",
        "major",
    }
)

# Normative wording ranks (ISO/IEC-style modality).
_MODALITY_RANK: dict[str, int] = {
    "shall": 3,
    "must": 3,
    "required": 3,
    "should": 2,
    "recommended": 2,
    "may": 1,
    "optional": 1,
    "can": 1,
    "might": 0,
}


def _canon_dimension(label: str) -> str:
    return (label or "").strip().lower().replace(" ", "_").replace("-", "_")


def _finding_map(item: Any) -> dict[str, Any]:
    """Normalize a review finding to a plain dict."""
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "to_dict") and callable(item.to_dict):
        return dict(item.to_dict())
    # dataclass / namespace
    out: dict[str, Any] = {}
    for key in (
        "id",
        "dimension",
        "category",
        "taxonomy",
        "severity",
        "message",
        "description",
        "resolved",
        "modality",
        "expected_modality",
        "actual_modality",
    ):
        if hasattr(item, key):
            out[key] = getattr(item, key)
    return out


def _finding_dimension(f: dict[str, Any]) -> str:
    for key in ("dimension", "category", "taxonomy"):
        raw = f.get(key)
        if raw:
            return _canon_dimension(str(raw))
    return ""


def _finding_severity(f: dict[str, Any]) -> str:
    return _canon_dimension(str(f.get("severity") or "info"))


def _finding_resolved(f: dict[str, Any], resolved_ids: set[str]) -> bool:
    if f.get("resolved") is True:
        return True
    fid = str(f.get("id") or "")
    return bool(fid and fid in resolved_ids)


def _modality_weakened(expected: str, actual: str) -> bool:
    """True when actual modality is weaker than expected (shall→may etc.)."""
    e = _canon_dimension(expected)
    a = _canon_dimension(actual)
    if not e or not a:
        return False
    er = _MODALITY_RANK.get(e)
    ar = _MODALITY_RANK.get(a)
    if er is None or ar is None:
        return False
    return ar < er


def is_rule_review_dimension(label: str) -> bool:
    """True if *label* is a known GB/T-Bench taxonomy dimension (or alias)."""
    d = _canon_dimension(label)
    if d in DEFAULT_RULE_REVIEW_DIMENSIONS:
        return True
    aliases = {
        "structure": "document_structure",
        "scope": "scope_alignment",
        "modality": "normative_modality",
        "terminology": "terminology_consistency",
        "cross_section": "cross_section_consistency",
        "consistency": "cross_section_consistency",
    }
    return aliases.get(d) in DEFAULT_RULE_REVIEW_DIMENSIONS


def analyze_rule_review(
    findings: Sequence[Any] | None = None,
    *,
    dimensions_checked: Sequence[str] | str | None = None,
    required_dimensions: Sequence[str] | None = None,
    resolved_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Summarize hierarchical rule-intensive review coverage and blockers.

    Public case: arXiv 2608.06312 GB/T-Bench — structured review of national
    standard documents across a hierarchical taxonomy (structure, scope,
    normative modality, terminology, cross-section consistency).

    Returns a dict with covered/missing dimensions, critical findings, and
    modality weakenings. Does not gate; use :func:`gate_rule_review`.
    """
    required = [
        _canon_dimension(x)
        for x in (required_dimensions or sorted(DEFAULT_RULE_REVIEW_DIMENSIONS))
        if _canon_dimension(x)
    ]
    resolved_set = {str(x) for x in (resolved_ids or []) if str(x)}

    checked: list[str] = []
    seen: set[str] = set()
    if dimensions_checked is not None:
        labels = (
            [dimensions_checked]
            if isinstance(dimensions_checked, str)
            else list(dimensions_checked)
        )
        for lab in labels:
            d = _canon_dimension(str(lab))
            if d and d not in seen:
                seen.add(d)
                checked.append(d)

    findings_list = [_finding_map(f) for f in (findings or [])]
    for f in findings_list:
        d = _finding_dimension(f)
        if d and d not in seen:
            seen.add(d)
            checked.append(d)

    missing = [d for d in required if d not in seen]

    critical: list[dict[str, Any]] = []
    modality_weakenings: list[dict[str, Any]] = []
    for f in findings_list:
        if _finding_resolved(f, resolved_set):
            continue
        sev = _finding_severity(f)
        if sev in CRITICAL_REVIEW_SEVERITIES:
            critical.append(f)
        exp = str(f.get("expected_modality") or "")
        act = str(f.get("actual_modality") or f.get("modality") or "")
        if exp and act and _modality_weakened(exp, act):
            modality_weakenings.append(f)

    return {
        "required_dimensions": required,
        "covered_dimensions": checked,
        "missing_dimensions": missing,
        "finding_count": len(findings_list),
        "critical_finding_count": len(critical),
        "critical_findings": critical,
        "modality_weakening_count": len(modality_weakenings),
        "modality_weakenings": modality_weakenings,
        "full_taxonomy": len(missing) == 0 and len(required) > 0,
    }


def gate_rule_review(
    findings: Sequence[Any] | None = None,
    *,
    dimensions_checked: Sequence[str] | str | None = None,
    required_dimensions: Sequence[str] | None = None,
    claim_approved: bool = False,
    claim_complete: bool = False,
    max_unresolved_critical: int = 0,
    require_full_taxonomy: bool = True,
    resolved_ids: Sequence[str] | None = None,
    refuse_modality_weakening: bool = True,
) -> GateOutcome:
    """Refuse approve/complete of rule-intensive reviews without taxonomy coverage.

    Public case: arXiv 2608.06312 *Benchmarking and Enhancing LLMs for
    Rule-Intensive Review of National Standard Documents* (GB/T-Bench).
    LLM reviewers that score only domain Q&A or claim "approved" without
    hierarchical checks (structure, scope alignment, normative modality,
    terminology consistency, cross-section consistency) are ornament.

    Rules:

    1. ``claim_approved`` or ``claim_complete`` with **zero** dimensions
       checked → **FAIL_LOUD** (phantom complete review).
    2. Required taxonomy dimensions missing → **FAIL** when
       ``require_full_taxonomy`` (default).
    3. Unresolved critical/major findings above
       ``max_unresolved_critical`` → **FAIL**.
    4. Normative modality weakened (shall→may etc.) → **FAIL** when
       ``refuse_modality_weakening``.
    5. Full taxonomy + no blocking findings → **PASS**.

    Args:
        findings: Review findings (dicts or objects with dimension/severity).
        dimensions_checked: Explicit taxonomy dimensions the reviewer covered.
        required_dimensions: Override default GB/T hierarchy.
        claim_approved: Reviewer claims the document is approved.
        claim_complete: Reviewer claims the review is complete.
        max_unresolved_critical: Max open critical/major findings allowed.
        require_full_taxonomy: Missing dimensions → FAIL.
        resolved_ids: Finding ids already fixed.
        refuse_modality_weakening: shall/must weakened to may/should → FAIL.
    """
    summary = analyze_rule_review(
        findings,
        dimensions_checked=dimensions_checked,
        required_dimensions=required_dimensions,
        resolved_ids=resolved_ids,
    )
    covered = tuple(summary["covered_dimensions"])
    missing = tuple(summary["missing_dimensions"])
    n_crit = int(summary["critical_finding_count"])
    crit_payloads = tuple(summary["critical_findings"])
    weak = tuple(summary["modality_weakenings"])
    claiming = claim_approved or claim_complete
    action = (
        "approve_review"
        if claim_approved
        else ("complete_review" if claim_complete else "rule_review")
    )

    if claiming and len(covered) == 0:
        return _fail_loud(
            "RULE-INTENSIVE/GB-T: claim_approved/complete with zero taxonomy "
            "dimensions checked - phantom rule-intensive review "
            "(arXiv 2608.06312); refuse approve without hierarchical coverage",
            action=action,
            high_risk=True,
            covered_dimensions=(),
            missing_dimensions=missing,
            critical_finding_count=n_crit,
            violation_count=0,
            violations=(),
        )

    if require_full_taxonomy and missing and claiming:
        return _fail(
            f"RULE-INTENSIVE/GB-T: incomplete hierarchical review - missing "
            f"dimensions {list(missing)}; required full taxonomy "
            f"{summary['required_dimensions']} (arXiv 2608.06312)",
            action=action,
            high_risk=True,
            covered_dimensions=covered,
            missing_dimensions=missing,
            critical_finding_count=n_crit,
            violation_count=len(missing),
            violations=tuple({"kind": "missing_dimension", "dimension": d} for d in missing),
        )

    if n_crit > max_unresolved_critical and claiming:
        return _fail(
            f"RULE-INTENSIVE/GB-T: {n_crit} unresolved critical/major "
            f"finding(s) exceed max={max_unresolved_critical} - refuse approve",
            action=action,
            high_risk=True,
            covered_dimensions=covered,
            missing_dimensions=missing,
            critical_finding_count=n_crit,
            violation_count=n_crit,
            violations=crit_payloads,
        )

    if refuse_modality_weakening and weak and claiming:
        return _fail(
            f"RULE-INTENSIVE/GB-T: {len(weak)} normative modality weakening(s) "
            f"(shall/must→weaker wording) - refuse approve",
            action=action,
            high_risk=True,
            covered_dimensions=covered,
            missing_dimensions=missing,
            critical_finding_count=n_crit,
            violation_count=len(weak),
            violations=weak,
        )

    # Non-claiming analysis path: still FAIL_LOUD if nothing to inspect at all
    if not claiming and len(covered) == 0 and not findings:
        return _fail_loud(
            "RULE-INTENSIVE/GB-T: empty review - no dimensions and no findings",
            action=action,
            high_risk=True,
            covered_dimensions=(),
            missing_dimensions=missing,
        )

    # When not claiming approve, missing taxonomy is advisory only (PASS with note)
    # unless require_full_taxonomy and we treat finalize-like analysis.
    if require_full_taxonomy and missing and not claiming:
        # still surface incompleteness as FAIL so CI can block "ready" flags
        return _fail(
            f"RULE-INTENSIVE/GB-T: taxonomy incomplete - missing {list(missing)}",
            action=action,
            high_risk=False,
            covered_dimensions=covered,
            missing_dimensions=missing,
            critical_finding_count=n_crit,
            violation_count=len(missing),
            violations=tuple({"kind": "missing_dimension", "dimension": d} for d in missing),
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"RULE-INTENSIVE ok: taxonomy covered={list(covered)} "
            f"critical={n_crit} claim_approved={claim_approved}"
        ),
        exit_code=0,
        action=action,
        human_required=False,
        high_risk=claiming,
        covered_dimensions=covered,
        missing_dimensions=(),
        critical_finding_count=n_crit,
        violation_count=0,
        violations=(),
    )


def assert_rule_review_ok(
    findings: Sequence[Any] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_rule_review` is ok."""
    outcome = gate_rule_review(findings, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
