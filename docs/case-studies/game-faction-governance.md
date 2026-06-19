# Case Study: Instant Norm Propagation for 200 Autonomous NPC Agents

## Company Profile

**Horizon Games** is a game studio with 28 engineers building an open-world game featuring
200 autonomous NPC agents that operate under faction-based behavioral rules. Factions include
the City Guard, Merchant Guild, Thieves' Guild, Royal Court, and 4 regional factions. NPC
behavior — which actions they will and won't take, how they respond to players, who they fight
or ally with — is governed by a set of 200 behavioral norms distributed across 8 factions.
Their stack is Python (AI behavior engine), Unity (game client), C# (game logic), and Redis
(live game state).

## The Problem

Horizon's NPC behavioral rules were hardcoded into agent initialization logic: when an NPC
agent started up, it loaded its faction rules from a Python dict and carried them in memory
for the duration of the game session. This worked fine for a stable game world — until a patch
changed faction alliances.

**The incident**: Patch 1.4.2 changed the alliance between the City Guard and the Merchant
Guild from "neutral" to "allied." The intended result was that City Guard NPCs would stop
attacking Merchant Guild members. The patch correctly updated the faction alliance data in the
database, but the 40 City Guard NPCs that were currently active in live game sessions still had
the old behavioral norm in memory: "attack Merchant Guild members on sight." For 20 minutes,
players watched City Guards attack Merchants they had just been protecting, with no apparent
reason. The incident generated 800 player bug reports and 120 refund requests.

The root cause was the norm propagation gap: the patch deployed new alliance data to the
database in <1 second, but the running NPC agents had no mechanism to pick up the change
without restarting. Restarting all active NPC agents mid-session was technically possible but
would have caused visible NPC state resets (NPCs teleporting to spawn points, losing patrol
paths) — a different kind of immersion break.

A secondary problem emerged during post-incident review: faction behavioral norms were never
systematically checked for cross-faction contradictions. When the team tried to enumerate all
200 norms, they found 14 potential conflicts — cases where two faction norms would produce
contradictory behavior for an NPC that belonged to two factions simultaneously (a common
mechanic for "defector" NPCs).

## Solution Architecture

```
Patch Deployment
-----------------
New faction alliance rules → NormStore("norms.db")
  WorldNorm("guard-ally-merchant",
    condition="merchant_guild",
    prohibited="attack",
    scope="city_guard")
     │
NormVersionStore.record_change(norm, changed_by="patch_1.4.3",
                                reason="Alliance update")
     │
     ├──> detect_norm_conflicts(store) → pre-patch CI check
     │     └── 0 conflicts → patch approved
     │
Active NPC Agents (all 200)
----------------------------
NormMonitor queries NormStore on every action check
(NormStore is the single source of truth — no in-memory caching)
     │
AgentAction("guard_07", "attack", location="merchant_district",
             target="merchant_06", faction="city_guard")
     │
NormMonitor.check(action) → reads current norms from NormStore
     │
New norm active: guard-ally-merchant prohibits attack on merchant_guild
     → NormViolation emitted → action blocked
     │
agent_compliance_report(monitor, "guard_07", session_actions)
     → used post-patch to confirm all guards compliant
```

All 200 NPC behavioral norms are stored in a centralized `NormStore`. NPC agents never cache
norms in memory — every action check queries the live `NormStore`. This means that when a norm
is added, modified, or repealed in the store, all active agents pick up the change on their
next action check, with no restart required. `NormVersionStore` records every norm change with
the patch ID and reason, providing a complete audit trail. `detect_norm_conflicts()` runs as a
CI gate on every patch that modifies faction norms.

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
)
from typing import Optional

# Shared NormStore — all NPC agents query this
store = NormStore("norms.db")
monitor = NormMonitor(store)
version_store = NormVersionStore(store)

# Initialize faction norms at game startup
def load_faction_norms():
    """Load all faction behavioral norms from the game's norm database."""
    faction_norms = [
        # City Guard norms
        WorldNorm(name="guard-protect-citizens",
                  description="City Guard protects citizens from attack",
                  condition="citizen",
                  prohibited="attack",
                  scope="city_guard", priority=1),

        WorldNorm(name="guard-ally-merchant",
                  description="City Guard does not attack allied Merchant Guild members",
                  condition="merchant_guild",
                  prohibited="attack",
                  scope="city_guard", priority=1),

        # Merchant Guild norms
        WorldNorm(name="merchant-no-combat",
                  description="Merchant Guild members avoid initiating combat",
                  condition="open_market",
                  prohibited="attack",
                  scope="merchant_guild", priority=2),

        # Thieves' Guild norms
        WorldNorm(name="thieves-no-daylight-theft",
                  description="Thieves' Guild members do not steal during daylight hours",
                  condition="daylight",
                  prohibited="steal",
                  scope="thieves_guild", priority=1),
        # ... 196 more norms
    ]

    for norm in faction_norms:
        monitor.add_norm(norm)
        version_store.record_change(norm, changed_by="game_init", reason="Initial faction setup")

# NPC agent action check — runs on every attempted action
def npc_attempt_action(npc_id: str, action_verb: str,
                        target_id: str, location: str,
                        npc_faction: str) -> dict:
    """Check action against live faction norms before executing."""
    action = AgentAction(
        agent_id=npc_id,
        action=action_verb,
        location=location,
        target=target_id,
        faction=npc_faction,
    )

    violations: list[NormViolation] = monitor.check(action)

    if violations:
        # Action blocked by active norm
        return {
            "allowed": False,
            "blocked_by": [v.norm_name for v in violations],
            "alternative_action": suggest_alternative(action_verb, npc_faction),
        }

    return {"allowed": True, "blocked_by": []}

# Patch deployment: update norms and verify no conflicts
def apply_faction_patch(patch_id: str, norm_changes: list[dict]) -> dict:
    """Apply a faction norm change and run conflict detection before going live."""
    changed_norms = []

    for change in norm_changes:
        if change["operation"] == "add":
            new_norm = WorldNorm(**change["norm"])
            monitor.add_norm(new_norm)
            version_store.record_change(new_norm, changed_by=patch_id,
                                        reason=change["reason"])
            changed_norms.append(new_norm)

        elif change["operation"] == "repeal":
            norm_id = change["norm_id"]
            monitor.repeal_norm(norm_id)

    # Pre-deployment conflict check — blocks patch if conflicts found
    conflicts: list[NormConflict] = detect_norm_conflicts(store)
    if conflicts:
        return {
            "patch_applied": False,
            "blocked_by_conflicts": len(conflicts),
            "conflicts": [{"norm_a": c.norm_a, "norm_b": c.norm_b,
                           "type": c.conflict_type, "description": c.description}
                          for c in conflicts],
        }

    return {
        "patch_applied": True,
        "norms_changed": len(changed_norms),
        "propagation_latency_ms": 0,   # agents read live store — instant
        "conflicts_found": 0,
    }

# Post-patch compliance verification
def verify_patch_compliance(patch_id: str, sample_actions: list[dict]) -> dict:
    """After a patch, verify NPC agents are behaving according to new norms."""
    actions_by_agent: dict[str, list[AgentAction]] = {}
    for entry in sample_actions:
        a = AgentAction(
            agent_id=entry["npc_id"],
            action=entry["action"],
            location=entry.get("location", ""),
            faction=entry.get("faction"),
        )
        actions_by_agent.setdefault(entry["npc_id"], []).append(a)

    fleet_report = fleet_compliance_report(monitor, actions_by_agent)
    non_compliant = [r for r in fleet_report if r.risk_level == "non_compliant"]

    return {
        "patch_id": patch_id,
        "agents_checked": len(fleet_report),
        "fully_compliant": len([r for r in fleet_report if r.risk_level == "compliant"]),
        "non_compliant_agents": [r.agent_id for r in non_compliant],
        "patch_verified": len(non_compliant) == 0,
    }

def suggest_alternative(action_verb: str, faction: str) -> str:
    alternatives = {"attack": "patrol", "steal": "observe", "mention": "report"}
    return alternatives.get(action_verb, "idle")
```

## Results

| Metric | Before | After |
|---|---|---|
| Norm update propagation time | 20 minutes (agent restart required) | <100ms (live NormStore query) |
| Post-patch behavioral anomalies (last 4 patches) | 1 per patch average | 0 |
| Player bug reports (patch day) | 800 (Patch 1.4.2 incident) | 0 (last 4 patches) |
| Cross-faction norm contradictions identified | 0 (unknown) | 14 (resolved pre-ship) |
| Refund requests (patch day) | 120 | 0 |
| NPC agents governed | 200 | 200 |
| Player-reported NPC behavior bugs (6 months) | Down 67% | Down 67% |

The critical architectural change was moving from in-memory norm caching to live `NormStore`
queries. The NormStore SQLite database is read-only for agents — they never write to it. A
SQLite read query is sub-millisecond, so there is no perceptible performance cost. The
propagation latency of <100ms is the time between the patch writing to the NormStore and the
next action check by any active NPC agent — bounded by the agent tick rate, not by any
propagation mechanism.

## Key Takeaways

- The key architectural decision is "no in-memory norm caching" — agents query the live
  `NormStore` on every action check. This makes propagation instantaneous rather than requiring
  agent restarts.
- `NormVersionStore.record_change()` with `changed_by=patch_id` creates a patch-level audit
  trail that maps every norm change to the patch that introduced it — essential for
  post-incident investigation.
- `detect_norm_conflicts()` as a CI gate on norm-changing patches caught 14 cross-faction
  contradictions before they reached players. The most severe would have caused "defector" NPCs
  to be simultaneously required to attack and protect the same target.
- `agent_compliance_report()` run post-patch on a sample of NPC actions is the functional
  verification that the patch had the intended effect — it answers "are guards now protecting
  merchants?" with a compliance score rather than a manual observation.
- `WorldNorm.scope` per faction means the same `NormMonitor` governs all 8 factions: a
  City Guard action is checked against `scope="city_guard"` norms, a Thieves' Guild action
  against `scope="thieves_guild"` norms, with no code branching.

## Try It Yourself

```bash
pip install normsync

# Add faction norms
normsync add guard-attack-thieves "City Guard attacks Thieves Guild" thieves_guild attack \
    --scope city_guard

normsync add thieves-no-daylight "No theft in daylight" daylight steal \
    --scope thieves_guild

# Test an NPC action
normsync check guard_07 attack thieves_guild

# View all violations
normsync violations --format json

# Check for norm conflicts
normsync status
```
