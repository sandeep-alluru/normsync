# Propagating GDPR Policy Updates to 50 AI Agents in Under 200ms

## Company Profile

**ClearPath Financial** is a mid-size fintech firm with 200 engineers running 50 AI agents
across 8 teams — loan underwriting, fraud detection, KYC/AML, reporting, audit, customer
communication, credit risk, and model ops. Their stack is Python (agent orchestration),
FastAPI (internal APIs), PostgreSQL (operational data), and a mix of LLM providers for
document analysis and customer-facing generation. They operate under GDPR, CCPA, and
PSD2 compliance obligations, with legal interpretations of those regulations updated
several times per year by their privacy counsel.

## The Problem

In Q3, ClearPath's legal team updated the firm's internal GDPR interpretation: where the
previous policy prohibited "PII in LLM prompts," the updated policy extended this to
"PII or financial data in LLM prompts." The change was documented in a Confluence page and
sent to engineering leads by email. Three weeks later, a routine GDPR audit found that 11
of the 50 AI agents were still transmitting financial data — account balances, transaction
histories, credit scores — in raw LLM prompts. None of them had been updated.

**The propagation problem**: ClearPath's agents received their behavioral constraints
through system prompts authored by individual team engineers. When the legal team updated
the GDPR interpretation, each engineering team was responsible for updating their own
agents' system prompts. This created a 3-to-6 week lag per team, during which agents
operated under a superseded policy. With policy updates occurring 4–6 times per year and
8 teams each managing their own update cycle, some agents were almost continuously
operating under outdated constraints.

**No enforcement layer**: Even after system prompts were updated, there was no mechanism
to verify that agent behavior had actually changed. The system prompt expressed an
intent, but the agent's actions were not checked against the policy in any structured
way. The Q3 audit surfaced 47 policy violations across the 3-week propagation window —
all of which had been technically prohibited but were only discoverable through manual
log review.

**Regulatory exposure**: When the firm's Data Protection Officer was asked by GDPR
supervisors to produce evidence of "appropriate technical measures" for AI behavioral
constraints, the only artifact available was the Confluence page and the email thread.
There was no timestamped record of when policies became active, which agents were
governed by them, or when agents came into compliance. Regulators flagged this as a
material gap.

## Solution Architecture

```
Legal Policy Layer
-------------------
Privacy counsel updates GDPR interpretation
→ WorldNorm("no-pii-or-financial-in-prompts",
    condition="llm_prompt pii",
    prohibited="transmit_sensitive",
    scope="global", priority=10)
→ NormStore("clearpath_compliance.db")
→ NormVersionStore.record_change(norm,
      changed_by="legal_team",
      reason="GDPR Q3 update: extend PII prohibition to financial data")
     │
     ├──> detect_norm_conflicts(store) → pre-deploy CI check
     │     └── 0 conflicts → policy approved, stored
     │
Agent Layer (50 agents, 8 teams)
---------------------------------
All agents share NormMonitor(store)
Policy change is in NormStore → no restart, no re-deploy
     │
AgentAction("loan-agent-01", "transmit_sensitive",
            location="llm_prompt pii underwriting_pipeline",
            target="account_balance_raw",
            faction="loan_underwriting")
     │
NormMonitor.check(action) → reads live NormStore
     → NormViolation emitted: norm "no-pii-or-financial-in-prompts"
     │
fleet_compliance_report(monitor, actions_by_agent)
     → AgentCompliance per agent, sorted worst-first
     │
Compliance Reporting Layer
---------------------------
DPO dashboard: weekly fleet compliance report
Regulator request: NormVersionStore.get_history("no-pii-or-financial-in-prompts")
                   → full timestamped audit trail with changed_by and reason
```

All 50 agents share a single `NormStore` as the source of truth for active compliance
policies. Each agent creates an `AgentAction` for every LLM prompt call and checks it
against the live `NormMonitor` before transmitting. Because `NormMonitor` reads active
norms from the `NormStore` on every `check()` call, a policy update written to the store
propagates to all 50 agents on their next action — no system prompt edits, no redeploys,
no per-team update cycles.

`NormVersionStore` records every policy change with the author, timestamp, and reason.
This produces the timestamped audit trail that regulators require: for any policy, the
firm can produce the exact moment it became active, who authorized it, and what it
replaced. `detect_norm_conflicts()` runs as a CI gate before any policy update is
approved, catching logical contradictions before they reach agents.

## Implementation

```python
from normsync import (
    WorldNorm,
    AgentAction,
    NormMonitor,
    NormStore,
    NormViolation,
    NormVersionStore,
    NormConflict,
    AgentCompliance,
    agent_compliance_report,
    fleet_compliance_report,
    detect_norm_conflicts,
    print_violations,
    to_json,
)

# Shared NormStore — all 50 agents query this single source of truth
store = NormStore("clearpath_compliance.db")
version_store = NormVersionStore(store)
monitor = NormMonitor(store)   # live NormStore: norm changes propagate automatically

# Q3 policy update: extend PII prohibition to financial data
def apply_gdpr_q3_update() -> WorldNorm:
    """Legal team broadens GDPR prohibition to include financial data in prompts."""
    updated_norm = WorldNorm(
        name="no-pii-or-financial-in-prompts",
        description=(
            "AI agents must not transmit PII or financial data (account balances, "
            "transaction histories, credit scores) in raw LLM prompts."
        ),
        condition="llm_prompt pii",
        prohibited="transmit_sensitive",
        scope="global",
        priority=10,
    )
    store.save_norm(updated_norm)
    version_store.record_change(
        updated_norm,
        changed_by="legal_team",
        reason="GDPR Q3 update: extend PII prohibition to include financial data",
    )
    return updated_norm

# Check for conflicts before the update goes live
def validate_policy_update(norm: WorldNorm) -> list[NormConflict]:
    """Run conflict detection. Block deployment if any contradiction found."""
    conflicts = detect_norm_conflicts(store)
    if conflicts:
        for c in conflicts:
            print(f"CONFLICT BLOCKED: {c.norm_a} vs {c.norm_b}")
            print(f"  Type: {c.conflict_type} — {c.description}")
    return conflicts

# Each agent calls this before every LLM prompt
def agent_prompt_gate(agent_id: str, team: str, prompt_context: str) -> bool:
    """Return True if the prompt is allowed; False and log a violation if not."""
    action = AgentAction(
        agent_id=agent_id,
        action="transmit_sensitive",
        location=f"llm_prompt pii {team}_pipeline",
        target=prompt_context,
        faction=team,
    )
    violations: list[NormViolation] = monitor.check(action)
    if violations:
        store.save_violation(violations[0])
        return False   # block the prompt
    return True

# Weekly DPO report: fleet compliance sorted worst-first
def generate_dpo_report(session_logs: dict[str, list[dict]]) -> list[AgentCompliance]:
    actions_by_agent: dict[str, list[AgentAction]] = {}
    for agent_id, entries in session_logs.items():
        actions_by_agent[agent_id] = [
            AgentAction(
                agent_id=agent_id,
                action=e["action"],
                location=e["context"],
                target=e.get("target", ""),
                faction=e.get("team", ""),
            )
            for e in entries
        ]
    return fleet_compliance_report(monitor, actions_by_agent)

# Regulator request: produce timestamped audit trail for any policy
def produce_gdpr_audit_trail(policy_name: str) -> list[dict]:
    history = version_store.get_history(policy_name)
    return [
        {
            "version": v.version,
            "changed_at": v.changed_at,
            "changed_by": v.changed_by,
            "reason": v.change_reason,
        }
        for v in history
    ]
```

## Results

| Metric | Before | After |
|---|---|---|
| Policy propagation to all 50 agents | 3–6 weeks (per-team manual updates) | <200ms (live NormStore query) |
| Agents on outdated policy after Q3 update | 11 (found 3 weeks later) | 0 (checked on next action) |
| GDPR violations in propagation window | 47 (3-week window) | 0 |
| Time to produce regulator audit trail | Days (Confluence search + email thread) | Seconds (NormVersionStore query) |
| Policy contradictions caught pre-deploy | 0 (no tooling) | 3 (resolved before activation) |
| Compliance team review effort | Manual log review, weekly | Automated fleet report, daily |

The architectural shift that produced the <200ms propagation figure is not a push
mechanism — it is the elimination of caching. Agents no longer hold policy state in
memory or in system prompts. Every action check queries the live `NormStore`. A SQLite
read against a 50-norm table is sub-millisecond; the 200ms figure is the upper bound on
propagation latency bounded by agent tick rate, not by any broadcast delay. When the
legal team commits a norm update, every agent in the fleet is effectively updated on
its next action.

## Key Takeaways

- Storing compliance policies as `WorldNorm` objects in a shared `NormStore` rather than
  in per-agent system prompts eliminates the propagation window entirely — agents cannot
  operate on a superseded policy because they never hold a local copy.
- `NormVersionStore.record_change()` with `changed_by` and `reason` directly satisfies the
  GDPR Article 25 ("data protection by design") documentation requirement — regulators
  receive a timestamped record of every policy change, not a wiki snapshot.
- `fleet_compliance_report()` sorted by `compliance_rate` ascending gives compliance teams
  the right default view: the highest-risk agents surface at the top, enabling triage
  before escalation thresholds are breached.
- `detect_norm_conflicts()` as a CI gate before policy activation caught three contradictions
  in ClearPath's first deployment — two of which would have caused agents to simultaneously
  prohibit and require the same action class.
- The `trend` field in `AgentCompliance` ("improving", "stable", "degrading") is the early
  warning signal for agents drifting toward non-compliance before any violation threshold
  is crossed.

## Try It Yourself

```bash
pip install normsync

# Apply the GDPR Q3 policy update
normsync add no-pii-or-financial-in-prompts \
    "Prohibit PII and financial data in LLM prompts" \
    "llm_prompt pii" transmit_sensitive \
    --scope global --priority 10

# Simulate an agent transmitting financial data in an LLM prompt
normsync check loan-agent-01 transmit_sensitive "llm_prompt pii underwriting_pipeline"

# View all violations
normsync violations

# Run the full cascade demo
python examples/compliance_policy_cascade.py
```
