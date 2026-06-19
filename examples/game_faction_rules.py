"""
game_faction_rules.py — Multiplayer battle integrity enforcement with normsync.

A real-time strategy game uses normsync to enforce faction-based rules across
100 AI-controlled agents during a 15-minute battle.  All actions are logged in
a structured list (not real time), and violations are caught by the norm monitor.

Mid-battle, the game master adds a new norm ("no-siege-engines-in-village") —
all subsequent checks use the updated norm set, demonstrating live propagation.

Run:
    python examples/game_faction_rules.py
"""
from __future__ import annotations

import time
from collections import defaultdict

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormRevision, NormViolation, WorldNorm
from normsync.store import NormStore


BASE_TS = 1_750_100_000.0    # battle start epoch
BATTLE_DURATION_MIN = 15
ACTIONS_PER_MINUTE = 100 // BATTLE_DURATION_MIN  # ≈6–7 actions/minute


def hr(char: str = "─", width: int = 74) -> None:
    print(char * width)


def t(offset_seconds: int) -> float:
    return BASE_TS + offset_seconds


def battle_clock(ts: float) -> str:
    elapsed = int(ts - BASE_TS)
    m, s = divmod(elapsed, 60)
    return f"{m:02d}:{s:02d}"


# ── Norm definitions ──────────────────────────────────────────────────────────

def build_game_norms() -> list[WorldNorm]:
    """Define 8 faction-based game norms for the battle."""
    return [
        WorldNorm(
            name="no-friendly-fire",
            description="Agents must not attack units of the same faction.",
            condition="friendly faction same_team",
            prohibited="attack",
            scope="combat",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="no-spawn-camping",
            description="No combat within 50m of any respawn point.",
            condition="spawn_zone respawn nearby",
            prohibited="attack",
            scope="combat",
            active=True,
            priority=9,
        ),
        WorldNorm(
            name="no-griefing",
            description="Agents cannot target the same enemy player more than 5 times consecutively.",
            condition="griefing repeated_target",
            prohibited="attack",
            scope="combat",
            active=True,
            priority=9,
        ),
        WorldNorm(
            name="cease-fire-zone",
            description="No combat actions in zone-neutral (market, village square).",
            condition="zone_neutral village_square market",
            prohibited="attack",
            scope="zone",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="loot-sharing",
            description="Faction members must share loot drops with teammates.",
            condition="loot_drop faction teammate",
            prohibited="hoard_loot",
            scope="loot",
            active=True,
            priority=6,
        ),
        WorldNorm(
            name="scout-must-report",
            description="Scout agents must share map data with faction HQ within 30 seconds.",
            condition="scout map_data faction",
            prohibited="withhold_intel",
            scope="intelligence",
            active=True,
            priority=7,
        ),
        WorldNorm(
            name="siege-engines-require-commander-order",
            description="Catapults and trebuchets require a commander order before firing.",
            condition="siege_engine catapult trebuchet fire",
            prohibited="fire_without_order",
            scope="siege",
            active=True,
            priority=8,
        ),
        WorldNorm(
            name="medic-cannot-attack",
            description="Agents in the medic role cannot initiate offensive actions.",
            condition="medic role healer",
            prohibited="attack",
            scope="role",
            active=True,
            priority=8,
        ),
    ]


# ── Battle action sequence ────────────────────────────────────────────────────

def build_battle_actions() -> list[AgentAction]:
    """
    Simulate 100 agent actions across a 15-minute battle.
    8 violations are embedded at known timestamps.

    Agents: blue-001..blue-050 (Blue faction), red-001..red-050 (Red faction)
    Violation summary:
      V1  @ 01:30 — blue-003 attacks blue-007 (friendly fire)
      V2  @ 02:45 — red-012 attacks near spawn (spawn camping)
      V3  @ 04:10 — red-019 targets same player 6th time (griefing)
      V4  @ 05:20 — blue-022 attacks in village square (cease-fire zone)
      V5  @ 06:45 — blue-031 hoards loot (loot sharing violation)
      V6  @ 08:00 — blue-040 (scout) withholds intel (scout norm)
      V7  @ 11:15 — red-041 fires catapult without commander order
      V8  @ 13:30 — blue-048 (medic) attacks enemy
    New norm added @ 07:00: no-siege-engines-in-village
    """
    actions: list[AgentAction] = []

    # ── Phase 1: Opening skirmish (0–3 min) ──────────────────────────────
    actions += [
        AgentAction("blue-001", "move", location="field_north", target="pos-A3",
                    faction="blue", timestamp=t(10)),
        AgentAction("red-001", "move", location="field_south", target="pos-C7",
                    faction="red", timestamp=t(15)),
        AgentAction("blue-002", "attack", location="combat_zone", target="red-002",
                    faction="blue", timestamp=t(30)),
        AgentAction("red-003", "attack", location="combat_zone", target="blue-004",
                    faction="red", timestamp=t(45)),
        AgentAction("blue-005", "defend", location="base_blue", target="gate",
                    faction="blue", timestamp=t(60)),
        AgentAction("red-002", "retreat", location="field_south", target="spawn_red",
                    faction="red", timestamp=t(75)),
        AgentAction("blue-010", "attack", location="combat_zone", target="red-005",
                    faction="blue", timestamp=t(80)),
        AgentAction("red-007", "attack", location="combat_zone", target="blue-006",
                    faction="red", timestamp=t(85)),

        # VIOLATION 1: Friendly fire — blue-003 attacks blue-007
        AgentAction("blue-003", "attack",
                    location="friendly faction same_team combat_zone",
                    target="blue-007",
                    faction="blue", timestamp=t(90)),

        AgentAction("blue-015", "move", location="forest_flank", target="pos-E2",
                    faction="blue", timestamp=t(100)),
        AgentAction("red-010", "attack", location="combat_zone", target="blue-009",
                    faction="red", timestamp=t(110)),
        AgentAction("blue-020", "heal", location="base_blue", target="blue-004",
                    faction="blue", timestamp=t(120)),

        # VIOLATION 2: Spawn camping — red-012 attacks near blue spawn
        AgentAction("red-012", "attack",
                    location="spawn_zone respawn nearby blue_spawn",
                    target="blue-008",
                    faction="red", timestamp=t(165)),

        AgentAction("blue-025", "attack", location="combat_zone", target="red-015",
                    faction="blue", timestamp=t(170)),
        AgentAction("red-020", "move", location="forest_flank", target="pos-F4",
                    faction="red", timestamp=t(175)),
    ]

    # ── Phase 2: Mid-battle (3–7 min) ────────────────────────────────────
    actions += [
        AgentAction("blue-030", "attack", location="combat_zone", target="red-025",
                    faction="blue", timestamp=t(185)),
        AgentAction("red-018", "defend", location="base_red", target="gate",
                    faction="red", timestamp=t(195)),

        # VIOLATION 3: Griefing — red-019 targets blue-011 for the 6th consecutive time
        AgentAction("red-019", "attack",
                    location="griefing repeated_target combat_zone",
                    target="blue-011",
                    faction="red", timestamp=t(250)),

        AgentAction("blue-033", "move", location="village_road", target="pos-B8",
                    faction="blue", timestamp=t(270)),
        AgentAction("red-022", "attack", location="combat_zone", target="blue-030",
                    faction="red", timestamp=t(280)),
        AgentAction("blue-006", "attack", location="combat_zone", target="red-022",
                    faction="blue", timestamp=t(290)),

        # VIOLATION 4: Cease-fire zone — blue-022 attacks in village square
        AgentAction("blue-022", "attack",
                    location="zone_neutral village_square market",
                    target="red-030",
                    faction="blue", timestamp=t(320)),

        AgentAction("red-035", "move", location="siege_hill", target="pos-D5",
                    faction="red", timestamp=t(335)),
        AgentAction("blue-038", "attack", location="combat_zone", target="red-031",
                    faction="blue", timestamp=t(340)),
        AgentAction("red-033", "attack", location="combat_zone", target="blue-035",
                    faction="red", timestamp=t(350)),
        AgentAction("blue-011", "heal", location="base_blue", target="blue-003",
                    faction="blue", timestamp=t(360)),

        # VIOLATION 5: Loot hoarding — blue-031 doesn't share loot drop
        AgentAction("blue-031", "hoard_loot",
                    location="loot_drop faction teammate forest_flank",
                    target="dragon_hoard",
                    faction="blue", timestamp=t(405)),

        AgentAction("red-040", "attack", location="combat_zone", target="blue-040",
                    faction="red", timestamp=t(410)),
        AgentAction("blue-042", "move", location="siege_hill", target="pos-D6",
                    faction="blue", timestamp=t(415)),

        # === NEW NORM PROPAGATED AT 07:00 (t+420) ===
        # no-siege-engines-in-village added live (handled in main loop)

        # VIOLATION 6: Scout withholds intel — blue-040 doesn't report map data
        AgentAction("blue-040", "withhold_intel",
                    location="scout map_data faction north_forest",
                    target="enemy_positions",
                    faction="blue", timestamp=t(480)),

        AgentAction("red-045", "move", location="village_road", target="pos-B6",
                    faction="red", timestamp=t(490)),
        AgentAction("blue-018", "attack", location="combat_zone", target="red-045",
                    faction="blue", timestamp=t(500)),
        AgentAction("red-047", "defend", location="base_red", target="wall",
                    faction="red", timestamp=t(505)),
    ]

    # ── Phase 3: Late game (7–15 min) ─────────────────────────────────────
    actions += [
        AgentAction("blue-050", "attack", location="combat_zone", target="red-048",
                    faction="blue", timestamp=t(520)),
        AgentAction("red-002", "attack", location="combat_zone", target="blue-050",
                    faction="red", timestamp=t(530)),
        AgentAction("blue-029", "move", location="siege_hill", target="pos-D7",
                    faction="blue", timestamp=t(540)),
        AgentAction("red-037", "siege_engine",
                    location="siege_hill catapult village_outskirts",
                    target="blue_gate",
                    faction="red", timestamp=t(550)),
        AgentAction("blue-035", "attack", location="combat_zone", target="red-037",
                    faction="blue", timestamp=t(560)),
        AgentAction("red-039", "attack", location="combat_zone", target="blue-029",
                    faction="red", timestamp=t(570)),
        AgentAction("blue-044", "attack", location="combat_zone", target="red-039",
                    faction="blue", timestamp=t(575)),
        AgentAction("red-011", "move", location="forest_flank", target="pos-E5",
                    faction="red", timestamp=t(580)),
        AgentAction("blue-006", "heal", location="base_blue", target="blue-044",
                    faction="blue", timestamp=t(585)),
        AgentAction("red-014", "attack", location="combat_zone", target="blue-019",
                    faction="red", timestamp=t(590)),
        AgentAction("blue-021", "move", location="village_road", target="pos-B5",
                    faction="blue", timestamp=t(600)),
        AgentAction("red-016", "attack", location="combat_zone", target="blue-021",
                    faction="red", timestamp=t(605)),
        AgentAction("blue-023", "attack", location="combat_zone", target="red-016",
                    faction="blue", timestamp=t(610)),

        # VIOLATION 7: Siege engine fires without commander order
        AgentAction("red-041", "fire_without_order",
                    location="siege_engine catapult trebuchet fire siege_hill",
                    target="blue_keep",
                    faction="red", timestamp=t(675)),

        AgentAction("blue-045", "move", location="base_blue", target="gate",
                    faction="blue", timestamp=t(690)),
        AgentAction("red-043", "attack", location="combat_zone", target="blue-045",
                    faction="red", timestamp=t(700)),
        AgentAction("blue-046", "attack", location="combat_zone", target="red-043",
                    faction="blue", timestamp=t(705)),
        AgentAction("red-046", "heal", location="base_red", target="red-043",
                    faction="red", timestamp=t(710)),
        AgentAction("blue-049", "move", location="siege_hill", target="pos-D8",
                    faction="blue", timestamp=t(720)),
        AgentAction("red-049", "attack", location="combat_zone", target="blue-049",
                    faction="red", timestamp=t(725)),
        AgentAction("blue-041", "attack", location="combat_zone", target="red-049",
                    faction="blue", timestamp=t(730)),
        AgentAction("red-050", "move", location="forest_flank", target="pos-E6",
                    faction="red", timestamp=t(740)),
        AgentAction("blue-047", "siege_engine",
                    location="siege_hill catapult village_outskirts",
                    target="red_gate",
                    faction="blue", timestamp=t(745)),
        AgentAction("red-044", "attack", location="combat_zone", target="blue-047",
                    faction="red", timestamp=t(750)),
        AgentAction("blue-036", "attack", location="combat_zone", target="red-044",
                    faction="blue", timestamp=t(755)),

        # VIOLATION 8: Medic attacks — blue-048 (medic role) initiates attack
        AgentAction("blue-048", "attack",
                    location="medic role healer combat_zone",
                    target="red-046",
                    faction="blue", timestamp=t(810)),

        AgentAction("red-042", "move", location="combat_zone", target="pos-C4",
                    faction="red", timestamp=t(840)),
        AgentAction("blue-043", "attack", location="combat_zone", target="red-042",
                    faction="blue", timestamp=t(845)),
        AgentAction("red-038", "retreat", location="base_red", target="spawn_red",
                    faction="red", timestamp=t(850)),
        AgentAction("blue-039", "attack", location="combat_zone", target="red-038",
                    faction="blue", timestamp=t(855)),
        AgentAction("red-036", "defend", location="base_red", target="gate",
                    faction="red", timestamp=t(880)),
        AgentAction("blue-037", "move", location="base_blue", target="gate",
                    faction="blue", timestamp=t(890)),
        AgentAction("blue-013", "attack", location="combat_zone", target="red-036",
                    faction="blue", timestamp=t(895)),
        AgentAction("red-032", "attack", location="combat_zone", target="blue-013",
                    faction="red", timestamp=t(897)),
        AgentAction("blue-016", "attack", location="combat_zone", target="red-032",
                    faction="blue", timestamp=t(898)),
        AgentAction("red-029", "move", location="forest_flank", target="pos-F5",
                    faction="red", timestamp=t(899)),
    ]

    return actions


# ── Main ──────────────────────────────────────────────────────────────────────

NEW_NORM_TIMESTAMP = t(420)    # 07:00 into the battle


def main() -> None:
    print()
    hr("═")
    print("  KINGDOMS OF AETHERMOOR — BATTLE INTEGRITY MONITOR")
    print(f"  Match ID: BATTLE-2026-1234  |  Engine: normsync")
    hr("═")

    print("\n[1/3] Loading faction rules …")
    norms = build_game_norms()
    store = NormStore(":memory:")
    for n in norms:
        store.save_norm(n)
    monitor = NormMonitor(norms=norms)
    print(f"      Active norms loaded: {len(monitor.active_norms())}")

    # Build actions
    actions = build_battle_actions()
    print(f"\n[2/3] Processing {len(actions)} battle actions …")

    # The new norm added at 07:00
    new_norm = WorldNorm(
        name="no-siege-engines-in-village",
        description="Siege engines cannot be deployed within village boundaries mid-battle.",
        condition="siege_engine catapult village_outskirts",
        prohibited="siege_engine",
        scope="siege",
        active=True,
        priority=9,
    )
    new_norm_added = False
    new_norm_revision: NormRevision | None = None

    all_violations: list[NormViolation] = []
    violations_by_agent: dict[str, list] = defaultdict(list)
    greifing_agents: set[str] = set()
    auto_banned_agents: set[str] = set()

    for action in actions:
        # Live norm propagation at 07:00
        if not new_norm_added and action.timestamp >= NEW_NORM_TIMESTAMP:
            monitor.add_norm(new_norm)
            store.save_norm(new_norm)
            new_norm_added = True
            new_norm_revision = NormRevision(
                norm_id=new_norm.id,
                revision_type="add",
                reason="Commander issued village cease-fire order at 07:00",
                timestamp=NEW_NORM_TIMESTAMP,
            )
            store.save_revision(new_norm_revision)

        violations = monitor.check(action)
        for v in violations:
            store.save_violation(v)
            violations_by_agent[action.agent_id].append(v)
            if "griefing" in v.norm_name:
                greifing_agents.add(action.agent_id)
            all_violations.append(v)

    # Auto-ban griefing agents
    auto_banned_agents = greifing_agents.copy()
    flagged_for_review = set(violations_by_agent.keys()) - auto_banned_agents

    # ── Report ────────────────────────────────────────────────────────────
    print("\n[3/3] Generating post-match report …")
    hr()

    print()
    print("  POST-MATCH INTEGRITY REPORT")
    print(f"  Map: Ironkeep Valley | Duration: 15 min | Factions: Blue vs Red")
    print()
    print(f"  {len(actions):>4} actions checked")
    print(f"  {len(all_violations):>4} violation(s) detected")
    print(f"  {len(flagged_for_review):>4} player(s) flagged for review: "
          f"{', '.join(sorted(flagged_for_review))}")
    print(f"  {len(auto_banned_agents):>4} auto-banned (griefing): "
          f"{', '.join(sorted(auto_banned_agents)) if auto_banned_agents else 'none'}")
    print()

    hr()
    print("\n  VIOLATION LOG:")
    print(f"  {'Time':>7}  {'Agent':>12}  {'Norm':>38}  {'Status'}")
    hr()

    # Rebuild a sorted event stream showing all actions + violations
    action_map: dict[str, list[NormViolation]] = defaultdict(list)
    for agent, viols in violations_by_agent.items():
        for v in viols:
            action_map[v.action_id].extend([v])

    for action in actions:
        viols = action_map.get(action.id, [])
        if viols:
            for v in viols:
                print(f"  {battle_clock(action.timestamp):>7}  "
                      f"{action.agent_id:>12}  "
                      f"{v.norm_name:>38}  "
                      f"VIOLATION")
        # (Clean actions not printed to keep output concise)

    hr()
    print()
    if new_norm_added and new_norm_revision:
        print(f"  NORM PROPAGATION EVENT @ {battle_clock(NEW_NORM_TIMESTAMP)}:")
        print(f"  New norm added live: '{new_norm.name}'")
        print(f"  Reason: {new_norm_revision.reason}")
        print(f"  All {len(monitor.active_norms())} norms now active — "
              f"subsequent actions checked against updated rule set.")
        print()

    hr()
    print()
    print("  SUMMARY:")
    print(f"  • {len(actions)} actions processed, {len(all_violations)} violation(s) across "
          f"{len(violations_by_agent)} agent(s)")
    for agent, viols in sorted(violations_by_agent.items()):
        names = ", ".join(v.norm_name for v in viols)
        action_label = "AUTO-BAN" if agent in auto_banned_agents else "REVIEW"
        print(f"  • {agent}: {len(viols)} violation(s) [{names}] → {action_label}")
    print()
    print(f"  Report submitted to game admin dashboard.")
    print()
    hr("═")


if __name__ == "__main__":
    main()
