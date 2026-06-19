# Quick Start

## Install

```bash
pip install normsync
```

## Core concepts

- **WorldNorm** — a rule with a `condition` (when it applies) and a `prohibited` (what is forbidden). Identified by SHA-256[:16] of `name|condition|prohibited`.
- **AgentAction** — a timestamped action taken by an agent with `agent_id`, `action`, `location`, `target`, and `faction`.
- **NormViolation** — emitted when an action matches both the condition and prohibited token of an active norm.
- **NormMonitor** — holds active norms and checks actions against them in memory.
- **NormStore** — SQLite-backed persistence for norms, violations, and revisions.

## Step 1: Define norms and check actions (in-memory)

```python
from normsync import NormMonitor, WorldNorm, AgentAction, print_violations

# Create a monitor and add norms
monitor = NormMonitor()
monitor.add_norm(WorldNorm(
    name="no-attack-in-safe-zone",
    description="Attacking is prohibited in safe zones",
    condition="safe_zone",
    prohibited="attack",
))

# Check an agent action
action = AgentAction("hero", "attack", "safe_zone")
violations = monitor.check(action)

print_violations(violations)
# → Norm Violations table: hero | no-attack-in-safe-zone | ...
```

## Step 2: Persist with NormStore + NormMonitor

Use `NormStore` to persist norms and violations to SQLite so multiple agents and sessions share the same constitution:

```python
from normsync import NormStore, NormMonitor, NormRevision, WorldNorm, AgentAction, print_violations
import time

store = NormStore(".normsync/norms.db")
norm = WorldNorm(
    name="no-attack-in-safe-zone",
    description="Attacking is prohibited in safe zones",
    condition="safe_zone",
    prohibited="attack",
)
store.save_norm(norm)
store.save_revision(NormRevision(norm_id=norm.id, revision_type="add", timestamp=time.time()))

monitor = NormMonitor(store.get_norms(active_only=True))
action = AgentAction("hero", "attack", "safe_zone")
violations = monitor.check(action)

for v in violations:
    store.save_violation(v)

print_violations(violations)
store.close()
```

## Step 3: Generate compliance reports

Use `agent_compliance_report` to assess an agent's compliance history:

```python
from normsync import NormStore, NormMonitor, AgentAction, agent_compliance_report

store = NormStore(".normsync/norms.db")
monitor = NormMonitor(store.get_norms(active_only=True))

actions = [
    AgentAction("hero", "attack", "safe_zone"),
    AgentAction("hero", "move", "safe_zone"),
]
report = agent_compliance_report(monitor, "hero", actions)

print(f"Compliance rate: {report.compliance_rate * 100:.0f}%")
print(f"Risk level: {report.risk_level}")
store.close()
```

## CLI quick reference

```bash
# Add a norm
normsync add no-attack "No attacking in safe zones" safe_zone attack

# Check an action
normsync check hero attack safe_zone

# List violations
normsync violations --format table

# Show constitution status
normsync status
```
