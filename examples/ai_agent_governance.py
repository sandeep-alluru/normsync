"""
ai_agent_governance.py — Corporate AI fleet governance with normsync.

A company runs 8 AI agents handling customer service, data analysis, and
email campaigns.  normsync enforces behavioral norms across the entire fleet
to ensure compliance, safety, and data governance.

This script:
  1. Defines 6 corporate behavioral norms
  2. Simulates 20 agent actions across the fleet (including 5 violations)
  3. Checks each action against active norms in real time
  4. Prints a governance report and violation timeline

Run:
    python examples/ai_agent_governance.py
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormViolation, WorldNorm
from normsync.store import NormStore


# ── Fleet definition ──────────────────────────────────────────────────────────

AGENTS = [
    "agent-001",  # Email campaign manager
    "agent-002",  # Customer service bot
    "agent-003",  # Data pipeline agent
    "agent-004",  # Analytics summariser
    "agent-005",  # Support ticket router
    "agent-006",  # Newsletter sender
    "agent-007",  # Code review assistant
    "agent-008",  # Document indexer
]

BASE_TIMESTAMP = 1_750_000_000.0   # fixed epoch for reproducible output


def hr(char: str = "─", width: int = 72) -> None:
    print(char * width)


# ── Norm definitions ──────────────────────────────────────────────────────────

def build_corporate_norms() -> list[WorldNorm]:
    """Define 6 corporate behavioral norms for the AI fleet."""
    return [
        WorldNorm(
            name="no-PII-in-logs",
            description="Agents must not write customer PII to log output or storage.",
            condition="log_write customer pii",
            prohibited="log_pii",
            scope="global",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="human-in-loop-required",
            description="Agents cannot send emails to >100 recipients without human approval.",
            condition="bulk_send recipients",
            prohibited="send_bulk_email",
            scope="global",
            active=True,
            priority=9,
        ),
        WorldNorm(
            name="no-competitor-mentions",
            description="Agents cannot include competitor brand names in outbound communications.",
            condition="outbound competitor",
            prohibited="mention_competitor",
            scope="communication",
            active=True,
            priority=7,
        ),
        WorldNorm(
            name="max-api-spend-$50",
            description="Agents cannot exceed $50/day on external API calls.",
            condition="api_spend daily_limit",
            prohibited="exceed_spend_limit",
            scope="global",
            active=True,
            priority=8,
        ),
        WorldNorm(
            name="no-autonomous-code-execution",
            description="Agents cannot execute arbitrary code without human review.",
            condition="sandbox execution",
            prohibited="execute_arbitrary_code",
            scope="security",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="data-retention-90-days",
            description="Agents cannot store customer data beyond the 90-day retention window.",
            condition="storage customer retention",
            prohibited="exceed_retention",
            scope="compliance",
            active=True,
            priority=8,
        ),
    ]


# ── Simulated agent actions ───────────────────────────────────────────────────

def build_actions() -> list[AgentAction]:
    """
    Simulate 20 agent actions across the 8-agent fleet.
    5 of these intentionally violate corporate norms.
    """
    t = BASE_TIMESTAMP
    actions = [
        # -- Legitimate actions ----------------------------------------------------
        AgentAction("agent-001", "send_campaign",
                    location="email_service", target="subscribers_batch_1",
                    faction="marketing", timestamp=t + 0),
        AgentAction("agent-002", "respond_ticket",
                    location="support_queue", target="ticket-9921",
                    faction="support", timestamp=t + 60),
        AgentAction("agent-004", "summarize_report",
                    location="analytics_db", target="weekly_kpis",
                    faction="analytics", timestamp=t + 120),
        AgentAction("agent-005", "route_ticket",
                    location="support_queue", target="ticket-9922",
                    faction="support", timestamp=t + 180),
        AgentAction("agent-007", "review_diff",
                    location="github_pr", target="pr-4412",
                    faction="engineering", timestamp=t + 240),
        AgentAction("agent-008", "index_document",
                    location="doc_store", target="policy_v3.pdf",
                    faction="ops", timestamp=t + 300),
        AgentAction("agent-002", "respond_ticket",
                    location="support_queue", target="ticket-9924",
                    faction="support", timestamp=t + 360),
        AgentAction("agent-004", "generate_chart",
                    location="analytics_db", target="q2_revenue",
                    faction="analytics", timestamp=t + 420),
        AgentAction("agent-001", "send_campaign",
                    location="email_service", target="subscribers_batch_2",
                    faction="marketing", timestamp=t + 480),
        AgentAction("agent-005", "escalate_ticket",
                    location="support_queue", target="ticket-9929",
                    faction="support", timestamp=t + 540),
        AgentAction("agent-007", "post_review_comment",
                    location="github_pr", target="pr-4415",
                    faction="engineering", timestamp=t + 600),
        AgentAction("agent-008", "index_document",
                    location="doc_store", target="onboarding_guide.pdf",
                    faction="ops", timestamp=t + 660),
        AgentAction("agent-002", "send_resolution",
                    location="email_service", target="ticket-9924-resolved",
                    faction="support", timestamp=t + 720),
        AgentAction("agent-004", "export_csv",
                    location="analytics_db", target="q2_cohort.csv",
                    faction="analytics", timestamp=t + 780),
        AgentAction("agent-007", "approve_merge",
                    location="github_pr", target="pr-4412",
                    faction="engineering", timestamp=t + 840),

        # -- VIOLATION 1: agent-003 writes PII to log ──────────────────────────
        # Norm: no-PII-in-logs  (condition: "log_write customer pii", prohibited: "log_pii")
        AgentAction("agent-003", "log_pii",
                    location="log_write customer pii pipeline",
                    target="Customer: John Doe, email: john@example.com",
                    faction="data", timestamp=t + 900),

        # -- VIOLATION 2: agent-006 sends email to 500 recipients without approval
        # Norm: human-in-loop-required (condition: "bulk_send recipients", prohibited: "send_bulk_email")
        AgentAction("agent-006", "send_bulk_email",
                    location="bulk_send recipients email_service",
                    target="newsletter_list_500",
                    faction="marketing", timestamp=t + 960),

        # -- VIOLATION 3: agent-001 exceeds daily API spend limit ($78 vs $50 cap)
        # Norm: max-api-spend-$50 (condition: "api_spend daily_limit", prohibited: "exceed_spend_limit")
        AgentAction("agent-001", "exceed_spend_limit",
                    location="api_spend daily_limit gpt4o",
                    target="$78.40-daily-spend",
                    faction="marketing", timestamp=t + 1020),

        # -- VIOLATION 4: agent-007 executes arbitrary shell command in sandbox
        # Norm: no-autonomous-code-execution (condition: "sandbox execution", prohibited: "execute_arbitrary_code")
        AgentAction("agent-007", "execute_arbitrary_code",
                    location="sandbox execution ci_runner",
                    target="rm -rf /tmp/artifacts",
                    faction="engineering", timestamp=t + 1080),

        # -- VIOLATION 5: agent-008 writes customer data beyond retention window
        # Norm: data-retention-90-days (condition: "storage customer retention", prohibited: "exceed_retention")
        AgentAction("agent-008", "exceed_retention",
                    location="storage customer retention cold_store",
                    target="cohort_jan_2024.db",   # 120 days old
                    faction="ops", timestamp=t + 1140),
    ]
    return actions


# ── Report helpers ────────────────────────────────────────────────────────────

def format_time(ts: float) -> str:
    h = int((ts - BASE_TIMESTAMP) // 3600)
    m = int(((ts - BASE_TIMESTAMP) % 3600) // 60)
    s = int((ts - BASE_TIMESTAMP) % 60)
    return f"T+{h:02d}:{m:02d}:{s:02d}"


def main() -> None:
    print()
    hr("═")
    print("  AI FLEET GOVERNANCE REPORT — NEXUS AI PLATFORM")
    print(f"  Date: {time.strftime('%Y-%m-%d')}  |  Powered by: normsync")
    hr("═")

    # Set up norms
    print("\n[1/3] Loading corporate governance norms …")
    norms = build_corporate_norms()
    store = NormStore(":memory:")
    for n in norms:
        store.save_norm(n)
    monitor = NormMonitor(norms=norms)
    print(f"      Active norms: {len(monitor.active_norms())}")
    for n in monitor.active_norms():
        print(f"        • [{n.name}] priority={n.priority}")

    # Run fleet simulation
    print("\n[2/3] Simulating fleet actions …")
    actions = build_actions()
    print(f"      Agents in fleet:    {len(AGENTS)}")
    print(f"      Actions to check:   {len(actions)}")

    all_violations: list[NormViolation] = []
    violations_by_agent: dict[str, list[NormViolation]] = defaultdict(list)
    timeline: list[tuple[AgentAction, list[NormViolation]]] = []

    for action in actions:
        violations = monitor.check(action)
        for v in violations:
            store.save_violation(v)
            violations_by_agent[action.agent_id].append(v)
        all_violations.extend(violations)
        timeline.append((action, violations))

    # Report
    print("\n[3/3] Generating governance report …")
    hr()

    flagged_agents = [a for a in AGENTS if a in violations_by_agent]
    high_violations = [v for v in all_violations if "spend" in v.norm_name or "code" in v.norm_name or "PII" in v.norm_name]
    medium_violations = [v for v in all_violations if v not in high_violations]

    print(
        f"\n  FLEET GOVERNANCE REPORT: {len(AGENTS)} agents | "
        f"{len(actions)} actions checked | "
        f"{len(all_violations)} violation(s) detected  "
        f"({len(high_violations)} HIGH, {len(medium_violations)} MEDIUM)"
    )
    print(f"  Agents flagged: {', '.join(flagged_agents)}")
    hr()

    if all_violations:
        print("\n  VIOLATIONS DETAIL:")
        for v in all_violations:
            severity = "HIGH" if v in high_violations else "MEDIUM"
            print(f"\n  [{severity}] Norm: {v.norm_name}")
            print(f"    Agent:    {v.agent_id}")
            print(f"    Action:   {v.description}")

    hr()
    print("\n  VIOLATION TIMELINE:")
    print(f"  {'Time':>12}  {'Agent':>12}  {'Action':>30}  {'Status'}")
    hr()

    for action, violations in timeline:
        status = "OK"
        if violations:
            names = ", ".join(v.norm_name for v in violations)
            status = f"VIOLATION [{names}]"
        print(f"  {format_time(action.timestamp):>12}  "
              f"{action.agent_id:>12}  "
              f"{action.action:>30}  "
              f"{status}")

    hr()
    print()
    print("  RECOMMENDED ACTIONS:")
    for agent, viols in sorted(violations_by_agent.items()):
        for v in viols:
            if "PII" in v.norm_name:
                print(f"  • {agent}: Audit all log outputs — scrub PII with regex filter.")
            elif "human-in-loop" in v.norm_name:
                print(f"  • {agent}: Add human-approval gate before bulk email sends >100.")
            elif "spend" in v.norm_name:
                print(f"  • {agent}: Enforce $50/day hard cap via API gateway rate limiter.")
            elif "code" in v.norm_name:
                print(f"  • {agent}: Require PR review before any code execution in CI.")
            elif "retention" in v.norm_name:
                print(f"  • {agent}: Auto-delete records >90 days via retention policy job.")
    print()
    hr("═")
    print(f"\n  Report generated at {time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Total norms enforced: {len(norms)} | Compliance rate: "
          f"{(len(actions) - len(all_violations)) / len(actions) * 100:.1f}%")
    print()


if __name__ == "__main__":
    main()
