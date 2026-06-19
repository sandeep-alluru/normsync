# Python API Reference

## Top-level exports

```python
from normsync import (
    WorldNorm,
    AgentAction,
    NormViolation,
    NormRevision,
    NormMonitor,
    NormStore,
    NormVersion,
    NormVersionStore,
    NormConflict,
    AgentCompliance,
    agent_compliance_report,
    fleet_compliance_report,
    detect_norm_conflicts,
    print_violations,
    to_json,
    to_markdown,
)
```

---

## Data classes (`normsync.norm`)

### `WorldNorm`

A normative rule governing agent behavior. ID is SHA-256[:16] of `name|condition|prohibited`.

```python
@dataclass
class WorldNorm:
    name: str
    description: str
    condition: str        # tokens that must appear in action fields
    prohibited: str       # token that must match action verb
    scope: str = "global"
    active: bool = True
    priority: int = 0
    id: str              # auto-set in __post_init__

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldNorm: ...
```

### `AgentAction`

A timestamped action taken by an agent.

```python
@dataclass
class AgentAction:
    agent_id: str
    action: str
    location: str = ""
    target: str = ""
    faction: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    id: str              # auto-set in __post_init__

    def to_dict(self) -> dict[str, Any]: ...
```

### `NormViolation`

Emitted when an agent action violates a norm.

```python
@dataclass
class NormViolation:
    norm_id: str
    norm_name: str
    action_id: str
    agent_id: str
    description: str
    severity: str = "warn"
    timestamp: float = 0.0
    id: str              # auto-set in __post_init__

    def to_dict(self) -> dict[str, Any]: ...
```

### `NormRevision`

Records when a norm is created, modified, or repealed.

```python
@dataclass
class NormRevision:
    norm_id: str
    revision_type: str   # "add", "repeal", "modify"
    reason: str = ""
    timestamp: float = 0.0
    id: str              # auto-set in __post_init__

    def to_dict(self) -> dict[str, Any]: ...
```

---

## `NormMonitor` (`normsync.monitor`)

In-memory norm checking engine.

```python
class NormMonitor:
    def __init__(self, norms: list[WorldNorm] | None = None) -> None: ...

    def add_norm(self, norm: WorldNorm) -> None:
        """Add a norm to the monitor."""

    def repeal_norm(self, norm_id: str) -> NormRevision | None:
        """Deactivate a norm by ID and return a NormRevision record."""

    def active_norms(self) -> list[WorldNorm]:
        """Return all currently active norms."""

    def check(self, action: AgentAction) -> list[NormViolation]:
        """Check action against all active norms. Returns list of violations."""
```

---

## `NormStore` (`normsync.store`)

SQLite-backed persistence for norms, violations, and revisions.

```python
class NormStore:
    def __init__(self, db_path: str = ":memory:") -> None: ...

    def save_norm(self, norm: WorldNorm) -> None:
        """Persist a norm (insert or replace)."""

    def get_norms(self, active_only: bool = False) -> list[WorldNorm]:
        """Retrieve all (or only active) norms."""

    def save_violation(self, v: NormViolation) -> None:
        """Persist a norm violation."""

    def get_violations(self) -> list[NormViolation]:
        """Retrieve all violations ordered by timestamp descending."""

    def save_revision(self, rev: NormRevision) -> None:
        """Persist a norm revision."""

    def get_revisions(self) -> list[NormRevision]:
        """Retrieve all revisions ordered by timestamp descending."""

    def close(self) -> None:
        """Close the database connection."""
```

---

## `NormVersionStore` (`normsync.versioning`)

Tracks the full history of norm changes using an extra SQLite table.

```python
@dataclass
class NormVersion:
    norm_id: str
    norm_name: str
    version: int
    changed_at: float
    changed_by: str
    change_reason: str
    previous_version: int | None

class NormVersionStore:
    def __init__(self, store: NormStore) -> None: ...

    def record_change(
        self, norm: WorldNorm, changed_by: str, reason: str
    ) -> NormVersion:
        """Record a norm change. Version auto-increments per norm."""

    def get_history(self, norm_name: str) -> list[NormVersion]:
        """Return all versions of a norm by name, newest first."""

    def get_norm_at(self, norm_name: str, timestamp: float) -> WorldNorm | None:
        """Get what a norm looked like at a specific point in time."""

    def diff_versions(
        self, norm_name: str, v1: int, v2: int
    ) -> dict[str, Any]:
        """Show what changed between two versions."""
```

---

## Conflict detection (`normsync.conflicts`)

```python
@dataclass
class NormConflict:
    norm_a: str
    norm_b: str
    conflict_type: str   # "logical_contradiction", "priority_ambiguity", "scope_overlap"
    description: str
    example_action: str

def detect_norm_conflicts(
    store: list[WorldNorm] | NormStore,
) -> list[NormConflict]:
    """Find norms that may contradict each other.

    Accepts either a list of WorldNorm objects or a NormStore instance.
    """
```

---

## Compliance reporting (`normsync.compliance`)

```python
@dataclass
class AgentCompliance:
    agent_id: str
    total_actions: int
    violations: int
    compliance_rate: float   # 0.0–1.0
    risk_level: str          # "low", "medium", "high"
    trend: str               # "improving", "stable", "worsening"
    violation_breakdown: dict[str, int]   # norm_name → count

def agent_compliance_report(
    monitor: NormMonitor,
    agent_id: str,
    actions: list[AgentAction],
) -> AgentCompliance:
    """Generate a compliance report for a single agent."""

def fleet_compliance_report(
    monitor: NormMonitor,
    actions: list[AgentAction],
) -> list[AgentCompliance]:
    """Generate compliance reports for all agents in a fleet."""
```

---

## Report formatters (`normsync.report`)

```python
def print_violations(
    violations: list[NormViolation],
    console: Console | None = None,
) -> None:
    """Print violations as a Rich table."""

def to_json(
    norms: list[WorldNorm],
    violations: list[NormViolation] | None = None,
) -> str:
    """Serialize norms and optionally violations to JSON."""

def to_markdown(
    norms: list[WorldNorm],
    violations: list[NormViolation] | None = None,
) -> str:
    """Render norms and violations as Markdown."""
```
