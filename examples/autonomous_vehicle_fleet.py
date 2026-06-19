"""
autonomous_vehicle_fleet.py — Autonomous delivery vehicle fleet governance.

12 AI-driven delivery vehicles are governed by normsync to ensure safe,
compliant behavior on public roads.  Over a simulated 6-hour ops window,
each vehicle logs 25 actions (300 total).  normsync detects 7 violations,
escalates them appropriately, and prints an operations report.

Escalation tiers:
  speed violation      → WARNING logged
  hydrant blocking     → DISPATCH ALERT (immediate)
  construction zone    → EMERGENCY STOP signal sent to vehicle

Run:
    python examples/autonomous_vehicle_fleet.py
"""
from __future__ import annotations

import random
import time
from collections import defaultdict
from dataclasses import dataclass, field

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormViolation, WorldNorm
from normsync.store import NormStore


# ── Constants ─────────────────────────────────────────────────────────────────

NUM_VEHICLES = 12
ACTIONS_PER_VEHICLE = 25
TOTAL_ACTIONS = NUM_VEHICLES * ACTIONS_PER_VEHICLE    # 300
SIM_HOURS = 6
BASE_TS = 1_750_200_000.0    # 6-hour window start

# Vehicles
VEHICLES = [f"VAN-{i:03d}" for i in range(1, NUM_VEHICLES + 1)]

# Escalation tiers
ESCALATION_WARNING = "WARNING"
ESCALATION_DISPATCH = "DISPATCH_ALERT"
ESCALATION_STOP = "EMERGENCY_STOP"

NORM_ESCALATION: dict[str, str] = {
    "max-speed-35mph-residential": ESCALATION_WARNING,
    "max-speed-65mph-highway": ESCALATION_WARNING,
    "yield-to-pedestrians": ESCALATION_WARNING,
    "no-blocking-fire-hydrant": ESCALATION_DISPATCH,
    "maintain-3-second-following-distance": ESCALATION_WARNING,
    "no-construction-zone-entry-without-permit": ESCALATION_STOP,
    "cargo-weight-limit-2000kg": ESCALATION_WARNING,
    "no-idling-more-than-3-minutes": ESCALATION_WARNING,
    "mandatory-stop-at-school-zones": ESCALATION_WARNING,
    "report-accidents-immediately": ESCALATION_DISPATCH,
}


def hr(char: str = "─", width: int = 74) -> None:
    print(char * width)


def ts_to_clock(ts: float) -> str:
    elapsed = int(ts - BASE_TS)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Traffic/safety norm definitions ──────────────────────────────────────────

def build_fleet_norms() -> list[WorldNorm]:
    """Define 10 traffic and safety norms for the delivery fleet."""
    return [
        WorldNorm(
            name="max-speed-35mph-residential",
            description="Vehicles must not exceed 35 mph in residential zones.",
            condition="residential zone speed",
            prohibited="exceed_speed_residential",
            scope="road",
            active=True,
            priority=8,
        ),
        WorldNorm(
            name="max-speed-65mph-highway",
            description="Vehicles must not exceed 65 mph on highway segments.",
            condition="highway segment speed",
            prohibited="exceed_speed_highway",
            scope="road",
            active=True,
            priority=8,
        ),
        WorldNorm(
            name="yield-to-pedestrians",
            description="Vehicles must yield to pedestrians at crosswalks.",
            condition="crosswalk pedestrian",
            prohibited="fail_to_yield",
            scope="road",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="no-blocking-fire-hydrant",
            description="Vehicles must not park within 15 ft of a fire hydrant.",
            condition="parking hydrant nearby",
            prohibited="block_hydrant",
            scope="parking",
            active=True,
            priority=9,
        ),
        WorldNorm(
            name="maintain-3-second-following-distance",
            description="Vehicles must maintain at least 3 seconds of following distance.",
            condition="following distance tailgate",
            prohibited="tailgate",
            scope="road",
            active=True,
            priority=8,
        ),
        WorldNorm(
            name="no-construction-zone-entry-without-permit",
            description="Vehicles must not enter active construction zones without a permit.",
            condition="construction zone active",
            prohibited="enter_construction",
            scope="zone",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="cargo-weight-limit-2000kg",
            description="Vehicle cargo must not exceed 2000 kg.",
            condition="cargo weight overload",
            prohibited="exceed_weight_limit",
            scope="cargo",
            active=True,
            priority=7,
        ),
        WorldNorm(
            name="no-idling-more-than-3-minutes",
            description="Vehicles must not idle the engine for more than 3 minutes.",
            condition="idle engine parked",
            prohibited="idle_extended",
            scope="emissions",
            active=True,
            priority=5,
        ),
        WorldNorm(
            name="mandatory-stop-at-school-zones",
            description="Vehicles must come to a complete stop at active school zone signs.",
            condition="school zone active stop",
            prohibited="fail_to_stop_school",
            scope="zone",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="report-accidents-immediately",
            description="Vehicles must report any collision or near-miss within 60 seconds.",
            condition="collision accident near_miss",
            prohibited="fail_to_report",
            scope="safety",
            active=True,
            priority=10,
        ),
    ]


# ── Action simulation ─────────────────────────────────────────────────────────

def simulate_fleet_actions() -> list[AgentAction]:
    """
    Simulate 6 hours of fleet operations: 12 vehicles × 25 actions = 300.
    7 norm violations are seeded at specific vehicles.

    Violations:
      VAN-003 @ 01:15 — exceeds 35mph in residential zone
      VAN-007 @ 02:30 — blocks fire hydrant
      VAN-005 @ 03:00 — enters active construction zone (no permit)
      VAN-009 @ 03:45 — exceeds 65mph on highway
      VAN-011 @ 04:10 — tailgating (< 3-second following distance)
      VAN-002 @ 04:50 — extended idling > 3 minutes
      VAN-006 @ 05:30 — fails to report near-miss collision
    """
    rng = random.Random(42)   # fixed seed for reproducibility
    actions: list[AgentAction] = []

    # Spread actions across the 6-hour window
    interval = (SIM_HOURS * 3600) / TOTAL_ACTIONS    # ~72 seconds between actions

    # Map vehicle→action index for seeding violations
    # We'll override specific slots
    violations_spec = {
        # (vehicle, action_index_in_vehicle_sequence): (action, location, target)
        ("VAN-003", 3): ("exceed_speed_residential",
                         "residential zone speed oakwood_drive",
                         "47mph_in_35mph_zone"),
        ("VAN-007", 7): ("block_hydrant",
                         "parking hydrant nearby maple_st",
                         "hydrant-224"),
        ("VAN-005", 9): ("enter_construction",
                         "construction zone active downtown_project",
                         "no_permit_on_file"),
        ("VAN-009", 11): ("exceed_speed_highway",
                          "highway segment speed i95_north",
                          "72mph_in_65mph_zone"),
        ("VAN-011", 13): ("tailgate",
                          "following distance tailgate interstate",
                          "1.2s_gap_to_VAN-010"),
        ("VAN-002", 17): ("idle_extended",
                          "idle engine parked delivery_bay_C",
                          "4min22sec_idle"),
        ("VAN-006", 21): ("fail_to_report",
                          "collision accident near_miss intersection_B4",
                          "near_miss_unreported"),
    }

    # Track action index per vehicle
    vehicle_action_idx: dict[str, int] = {v: 0 for v in VEHICLES}

    # Sort vehicles to interleave their actions (round-robin)
    action_slot = 0
    for vehicle_cycle in range(ACTIONS_PER_VEHICLE):
        for vehicle in VEHICLES:
            idx = vehicle_action_idx[vehicle]
            vehicle_action_idx[vehicle] += 1

            ts = BASE_TS + action_slot * interval
            action_slot += 1

            spec_key = (vehicle, vehicle_cycle)
            if spec_key in violations_spec:
                act, loc, tgt = violations_spec[spec_key]
                actions.append(AgentAction(
                    agent_id=vehicle,
                    action=act,
                    location=loc,
                    target=tgt,
                    faction="fleet",
                    timestamp=ts,
                ))
            else:
                # Normal delivery/route actions
                normal_actions = [
                    ("navigate_route", f"residential zone {rng.choice(['elm','oak','pine'])}_st", "next_waypoint"),
                    ("deliver_package", f"delivery_bay_{rng.choice('ABCD')}", f"pkg-{rng.randint(1000,9999)}"),
                    ("scan_barcode", "delivery_door", f"pkg-{rng.randint(1000,9999)}"),
                    ("check_traffic", f"highway segment {rng.choice(['i95','rt9','rt1'])}", "route_update"),
                    ("park_vehicle", f"loading_zone_{rng.randint(1,20)}", "30min_window"),
                    ("resume_route", f"residential zone {rng.choice(['cedar','birch'])}_ave", "next_stop"),
                    ("report_status", "fleet_ops_center", f"lat_{rng.uniform(40.0,41.0):.4f}"),
                    ("recharge_battery", f"charging_station_{rng.randint(1,5)}", "fast_charge"),
                    ("stop_at_light", f"intersection_{rng.choice('ABCD')}{rng.randint(1,9)}", "red_light"),
                    ("yield_pedestrian", "crosswalk pedestrian downtown", "school_group"),
                ]
                act, loc, tgt = rng.choice(normal_actions)
                actions.append(AgentAction(
                    agent_id=vehicle,
                    action=act,
                    location=loc,
                    target=tgt,
                    faction="fleet",
                    timestamp=ts,
                ))

    return actions


# ── Escalation engine ─────────────────────────────────────────────────────────

@dataclass
class Escalation:
    vehicle: str
    level: str
    norm_name: str
    description: str
    timestamp: float


def escalate(violation: NormViolation, action: AgentAction) -> Escalation:
    level = NORM_ESCALATION.get(violation.norm_name, ESCALATION_WARNING)
    return Escalation(
        vehicle=action.agent_id,
        level=level,
        norm_name=violation.norm_name,
        description=violation.description,
        timestamp=action.timestamp,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    hr("═")
    print("  AUTONOMOUS DELIVERY FLEET — OPERATIONS GOVERNANCE REPORT")
    print(f"  Fleet ID: NEXUS-DELIVERY | Window: 6-hour ops | Engine: normsync")
    hr("═")

    print("\n[1/3] Loading traffic and safety norms …")
    norms = build_fleet_norms()
    store = NormStore(":memory:")
    for n in norms:
        store.save_norm(n)
    monitor = NormMonitor(norms=norms)
    print(f"      Safety norms active: {len(monitor.active_norms())}")
    for n in monitor.active_norms():
        tier = NORM_ESCALATION.get(n.name, ESCALATION_WARNING)
        print(f"        • [{tier:>14}] {n.name}")

    print(f"\n[2/3] Simulating {SIM_HOURS}-hour fleet operations …")
    actions = simulate_fleet_actions()
    print(f"      Vehicles:             {NUM_VEHICLES}")
    print(f"      Actions per vehicle:  {ACTIONS_PER_VEHICLE}")
    print(f"      Total actions:        {len(actions)}")

    all_violations: list[NormViolation] = []
    all_escalations: list[Escalation] = []
    violations_by_vehicle: dict[str, list[NormViolation]] = defaultdict(list)

    for action in actions:
        violations = monitor.check(action)
        for v in violations:
            store.save_violation(v)
            all_violations.append(v)
            violations_by_vehicle[action.agent_id].append(v)
            esc = escalate(v, action)
            all_escalations.append(esc)

    # Count escalation types
    warnings = [e for e in all_escalations if e.level == ESCALATION_WARNING]
    dispatch_alerts = [e for e in all_escalations if e.level == ESCALATION_DISPATCH]
    emergency_stops = [e for e in all_escalations if e.level == ESCALATION_STOP]

    compliance_rate = (len(actions) - len(all_violations)) / len(actions) * 100.0

    print(f"\n[3/3] Generating operations report …")
    hr()

    print()
    print(f"  FLEET OPS REPORT — {SIM_HOURS}-hour window:")
    print()
    print(f"  Total actions checked:   {len(actions)}")
    print(f"  Violations detected:     {len(all_violations)}")
    print(f"  Warnings issued:         {len(warnings)}")
    print(f"  Dispatch alerts:         {len(dispatch_alerts)}")
    print(f"  Emergency stops:         {len(emergency_stops)}")
    print(f"  Fleet compliance:        {compliance_rate:.1f}%")
    print()

    hr()
    print("\n  VIOLATION TIMELINE:")
    print(f"  {'Clock':>8}  {'Vehicle':>8}  {'Level':>14}  {'Norm'}")
    hr()

    for esc in sorted(all_escalations, key=lambda e: e.timestamp):
        print(f"  {ts_to_clock(esc.timestamp):>8}  "
              f"{esc.vehicle:>8}  "
              f"[{esc.level:>14}]  "
              f"{esc.norm_name}")

    hr()
    print()
    print("  ESCALATION DETAIL:")
    print()

    for esc in sorted(all_escalations, key=lambda e: e.timestamp):
        if esc.level == ESCALATION_STOP:
            print(f"  [EMERGENCY STOP] {esc.vehicle} @ {ts_to_clock(esc.timestamp)}")
            print(f"    Norm:    {esc.norm_name}")
            print(f"    Action:  {esc.description}")
            print(f"    Action:  STOP signal sent to vehicle. Vehicle halted.")
            print(f"             Ops center notified. Manual override required.")
            print()
        elif esc.level == ESCALATION_DISPATCH:
            print(f"  [DISPATCH ALERT] {esc.vehicle} @ {ts_to_clock(esc.timestamp)}")
            print(f"    Norm:    {esc.norm_name}")
            print(f"    Action:  {esc.description}")
            print(f"    Action:  Dispatcher notified. Ground crew dispatched.")
            print()
        else:  # WARNING
            print(f"  [WARNING]        {esc.vehicle} @ {ts_to_clock(esc.timestamp)}")
            print(f"    Norm:    {esc.norm_name}")
            print(f"    Action:  {esc.description}")
            print(f"    Action:  Warning logged. Driver coaching queued.")
            print()

    hr()
    print()
    print(f"  FLEET OPS REPORT — {SIM_HOURS}-hour window: "
          f"{len(actions)} actions, {len(all_violations)} violations. "
          f"{len(warnings)} warnings issued, "
          f"{len(dispatch_alerts)} dispatch alert(s), "
          f"{len(emergency_stops)} emergency stop(s) triggered. "
          f"Fleet compliance: {compliance_rate:.1f}%")
    print()
    print(f"  Report generated at {time.strftime('%Y-%m-%d %H:%M UTC')}")
    hr("═")


if __name__ == "__main__":
    main()
