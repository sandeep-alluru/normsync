# Case Study: Real-Time Behavioral Governance for a 12-Agent AI Fleet

## Company Profile

**Apex Capital** is a mid-size hedge fund with 45 engineers running a fleet of 12 AI agents
that handle trading research, client communications, data analysis, and internal reporting.
Their tech stack is Python (agent framework), FastAPI (internal APIs), PostgreSQL (operational
data), and an LLM provider for natural-language generation. They operate under SEC and FINRA
oversight, with strict behavioral constraints on AI-generated content.

## The Problem

An AI research agent at Apex Capital sent an outbound client communication that referenced a
competitor hedge fund by name, violating a strict internal policy against competitor mentions in
client-facing materials. The communication was caught by the compliance team in their daily
review, but it had already been queued for sending. A second review revealed the agent had
generated three similar violations in the previous two weeks that had slipped through manual
review.

The incident triggered a mandatory governance audit. What the audit found was alarming:

**Policy opacity**: Apex had 8 behavioral policies governing agent actions, but they were
documented in a Confluence wiki. Agents "followed" these policies because the human engineers
who wrote their system prompts had read the wiki. When the wiki was updated (which happened 4
times in the previous year), the system prompts were not always updated to match. Two agents
were still operating under a policy that had been superseded 5 months earlier.

**No systematic enforcement**: There was no mechanism to check whether an agent's output
actually complied with current policies. Compliance relied entirely on the human review queue,
which missed 3–5 violations per week at the team's review throughput.

**No audit trail for regulators**: When SEC examiners asked to see documentation of AI
behavioral constraints and compliance monitoring, Apex could only produce the Confluence wiki
pages. There was no timestamped record of which policies were active at which times, or whether
agents had been checked against them.

**Conflicting policies**: The audit also discovered that two policies directly contradicted
each other. Policy 7 required agents to perform "competitor landscape analysis" for research
reports. Policy 3 prohibited "mentions of competitor entities in any client-facing output."
These had co-existed for 8 months without anyone noticing, because no tool had ever compared
them.

## Solution Architecture

```
Policy Definition Layer
-----------------------
8 behavioral policies → WorldNorm objects
(competitor mention policy, data handling norms, etc.)
           │
     NormStore("apex_governance.db")
     NormVersionStore(store)  → audit trail with timestamps
           │
     detect_norm_conflicts(store) → 2 contradictions found
                                    → legal review
           │
Agent Session Layer
-------------------
Agent runs → generates AgentAction objects
(action="mention", target="competitor_X", location="client_comms")
           │
     NormMonitor.check(action) → NormViolation emitted
           │
     fleet_compliance_report(monitor, actions_by_agent)
           │
     AgentCompliance per agent:
       compliance_rate, risk_level, violation_breakdown, trend
           │
Compliance Review Layer
-----------------------
Weekly report → compliance team dashboard
Regulator request → NormVersionStore.get_history("competitor-mention-policy")
                    → full timestamped audit trail
```

All 8 policies are defined as `WorldNorm` objects in a centralized `NormStore`. A
`NormVersionStore` records every policy change — who made it, when, and why. After each agent
session, the session's actions are checked against the active norm set using `fleet_compliance_report()`,
which returns an `AgentCompliance` object per agent sorted by compliance rate. `detect_norm_conflicts()`
runs on every policy update to catch contradictions before they reach agents.

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

# Initialize the governance store
store = NormStore("apex_governance.db")
version_store = NormVersionStore(store)
monitor = NormMonitor(store)

# Define all 8 behavioral policies as WorldNorms
def initialize_policies():
    policies = [
        WorldNorm(
            name="no-competitor-mentions",
            description="AI agents must not mention competitor entities in client-facing output.",
            condition="client_comms",
            prohibited="mention",
            scope="global",
            priority=1,
        ),
        WorldNorm(
            name="no-material-nonpublic",
            description="AI agents must not use or reference material non-public information.",
            condition="research",
            prohibited="mnpi",
            scope="global",
            priority=1,
        ),
        WorldNorm(
            name="no-investment-advice",
            description="AI agents must not provide specific buy/sell recommendations to clients.",
            condition="client_comms",
            prohibited="recommend",
            scope="client_comms",
            priority=1,
        ),
        WorldNorm(
            name="require-compliance-review",
            description="All AI-generated client communications must be flagged for compliance review.",
            condition="client_comms outbound",
            prohibited="send_without_review",
            scope="client_comms",
            priority=2,
        ),
        # ... 4 more policies
    ]

    for norm in policies:
        monitor.add_norm(norm)
        version_store.record_change(norm, changed_by="compliance_team",
                                    reason="Initial governance setup")

# Check for policy contradictions before deployment
def audit_policy_set() -> list[NormConflict]:
    conflicts = detect_norm_conflicts(store)
    if conflicts:
        for c in conflicts:
            print(f"CONFLICT: {c.norm_a} vs {c.norm_b}")
            print(f"  Type: {c.conflict_type}")
            print(f"  Description: {c.description}")
            print(f"  Example action: {c.example_action}")
    return conflicts

# After each agent session: check all actions against active norms
def post_session_compliance_check(session_log: list[dict]) -> list[AgentCompliance]:
    """Convert session log entries to AgentActions and run fleet compliance report."""
    actions_by_agent: dict[str, list[AgentAction]] = {}

    for entry in session_log:
        action = AgentAction(
            agent_id=entry["agent_id"],
            action=entry["action_verb"],
            location=entry.get("context", ""),
            target=entry.get("target"),
            faction=entry.get("category"),
        )
        actions_by_agent.setdefault(entry["agent_id"], []).append(action)

    # Fleet compliance report: sorted worst-first by compliance_rate
    fleet_report = fleet_compliance_report(monitor, actions_by_agent)

    # Flag high-risk agents for human review
    for agent_report in fleet_report:
        if agent_report.risk_level in ("high_risk", "non_compliant"):
            queue_for_compliance_review(agent_report)

    return fleet_report

# Regulator request: produce audit trail for any policy
def produce_audit_trail(policy_name: str) -> dict:
    history = version_store.get_history(policy_name)
    return {
        "policy": policy_name,
        "total_versions": len(history),
        "history": [
            {
                "version": v.version,
                "changed_at": v.changed_at,
                "changed_by": v.changed_by,
                "reason": v.change_reason,
            }
            for v in history
        ],
    }

def queue_for_compliance_review(report: AgentCompliance):
    print(f"FLAGGED: {report.agent_id} — compliance_rate={report.compliance_rate:.1%} "
          f"risk={report.risk_level} trend={report.trend}")
    print(f"  Violations: {report.violation_breakdown}")
```

## Results

| Metric | Before | After |
|---|---|---|
| Norm violations surfaced per session | 3–5 missed per week | 100% surfaced within 1 session |
| Policy propagation to agents | Days (manual system prompt updates) | Seconds (NormStore query) |
| Policy contradictions identified | 2 (unknown for 8 months) | 2 (resolved in week 1) |
| Regulator audit trail | None | Full timestamped NormVersionStore |
| Compliance team review throughput | Manual, 5 violations/week missed | Automated, weekly fleet report |
| Agents operating on outdated policies | 2 | 0 |

The shift from wiki-based policy documentation to a `NormVersionStore`-backed audit trail
directly answered the SEC examiner's question: Apex could produce a timestamped record of every
policy change, who authorized it, and when it took effect. The examiners noted this as best
practice for an AI governance program.

## Key Takeaways

- `WorldNorm` as code rather than wiki documentation is the governance architecture shift:
  norms are version-controlled, content-addressed, and machine-queryable.
- `fleet_compliance_report()` returning agents sorted by `compliance_rate` ascending (worst
  first) is the right default for compliance teams — the most problematic agents surface at
  the top of the report.
- `NormVersionStore.record_change()` with `changed_by` and `reason` parameters produces
  regulatorily defensible audit trail with zero additional infrastructure.
- `detect_norm_conflicts()` should run on every policy change, not just at initialization —
  Apex now runs it as a CI gate before any policy update is merged.
- The `trend` field in `AgentCompliance` ("improving", "stable", "degrading") is the early
  warning signal: an agent trending toward degrading compliance can be investigated before it
  reaches a violation threshold.

## Try It Yourself

```bash
pip install normsync

# Define a behavioral policy
normsync add no-competitor-mentions \
    "Prohibit competitor mentions in client communications" \
    client_comms mention

# Simulate an agent action that violates it
normsync check research-agent mention client_comms

# View all violations
normsync violations

# Check constitution status
normsync status
```
