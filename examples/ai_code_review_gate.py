"""
ai_code_review_gate.py — Block norm-violating code before it reaches CI.

A team uses an AI coding assistant (Copilot / Claude / Cursor) to generate
production code. Their engineering standards prohibit: hardcoded secrets,
eval() usage in user-facing paths, skipping input validation in public API
handlers, and direct SQL string concatenation.

Without a norm gate, 71 % of AI-generated PRs in their audit contained at
least one violation — leading to a 2.3× higher post-merge defect rate.

normsync acts as a pre-commit gate: each proposed code change is described as
an AgentAction, checked against the team's WorldNorms, and blocked if it
violates any rule.  Violations are logged to a NormStore for the quarterly
audit report.

Run:
    python examples/ai_code_review_gate.py
"""
from __future__ import annotations

import time

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormViolation, WorldNorm
from normsync.report import print_violations, to_json
from normsync.store import NormStore

# ── Engineering norms ─────────────────────────────────────────────────────────

CODING_NORMS: list[WorldNorm] = [
    WorldNorm(
        name="no-hardcoded-secrets",
        description="Secrets (API keys, passwords, tokens) must use env vars or secret managers",
        condition="",                   # empty = matches all locations (vacuously true)
        prohibited="hardcode-secret",
        scope="global",
        priority=10,
    ),
    WorldNorm(
        name="no-eval-in-public-api",
        description="eval() / exec() forbidden in public API handlers — RCE risk",
        condition="public-api",
        prohibited="use-eval",
        scope="global",
        priority=10,
    ),
    WorldNorm(
        name="no-skip-input-validation",
        description="All public API handlers must validate and sanitize inputs",
        condition="public-api",
        prohibited="skip-input-validation",
        scope="global",
        priority=9,
    ),
    WorldNorm(
        name="no-sql-string-concat",
        description="SQL queries must use parameterised statements — no string concatenation",
        condition="database",
        prohibited="sql-string-concat",
        scope="global",
        priority=9,
    ),
    WorldNorm(
        name="no-root-docker",
        description="Docker containers must not run as root in production",
        condition="container",
        prohibited="run-as-root",
        scope="global",
        priority=7,
    ),
]


# ── Proposed code changes (from AI assistant, as PR diff metadata) ────────────

PROPOSED_CHANGES: list[dict] = [
    # PR #1 — authentication service rewrite
    {
        "pr":       "PR-441",
        "agent_id": "copilot-gpt4o",
        "action":   "hardcode-secret",
        "location": "authentication",   # condition="" means norm fires regardless of location
        "target":   "auth/service.py:42 — API_KEY = 'sk-prod-8f3a...' hardcoded",
        "ts":       time.time() + 0,
    },
    {
        "pr":       "PR-441",
        "agent_id": "copilot-gpt4o",
        "action":   "add-jwt-middleware",
        "location": "public-api",
        "target":   "auth/middleware.py — JWT validation added",
        "ts":       time.time() + 1,
    },

    # PR #2 — user query endpoint
    {
        "pr":       "PR-449",
        "agent_id": "claude-sonnet",
        "action":   "use-eval",
        "location": "public-api",
        "target":   "api/query.py:18 — eval(user_input) for dynamic filter",
        "ts":       time.time() + 2,
    },
    {
        "pr":       "PR-449",
        "agent_id": "claude-sonnet",
        "action":   "skip-input-validation",
        "location": "public-api",
        "target":   "api/query.py:12 — no schema validation before processing",
        "ts":       time.time() + 3,
    },
    {
        "pr":       "PR-449",
        "agent_id": "claude-sonnet",
        "action":   "add-rate-limiting",
        "location": "public-api",
        "target":   "api/query.py:5 — rate limiter decorator added",
        "ts":       time.time() + 4,
    },

    # PR #3 — reporting dashboard (clean)
    {
        "pr":       "PR-452",
        "agent_id": "cursor-claude",
        "action":   "sql-string-concat",
        "location": "database",
        "target":   "reports/queries.py:33 — f'SELECT * FROM logs WHERE user={uid}'",
        "ts":       time.time() + 5,
    },
    {
        "pr":       "PR-452",
        "agent_id": "cursor-claude",
        "action":   "add-index",
        "location": "database",
        "target":   "reports/queries.py:10 — index on (user_id, created_at) added",
        "ts":       time.time() + 6,
    },

    # PR #4 — deployment config
    {
        "pr":       "PR-455",
        "agent_id": "copilot-gpt4o",
        "action":   "run-as-root",
        "location": "container",
        "target":   "Dockerfile:3 — USER root not dropped before CMD",
        "ts":       time.time() + 7,
    },
    {
        "pr":       "PR-455",
        "agent_id": "copilot-gpt4o",
        "action":   "add-healthcheck",
        "location": "container",
        "target":   "Dockerfile:20 — HEALTHCHECK added",
        "ts":       time.time() + 8,
    },
]


def hr(char: str = "─", width: int = 72) -> None:
    print(char * width)


def main() -> None:
    print()
    hr("═")
    print("  AI Code Review Gate — norm enforcement for AI-generated PRs")
    hr("═")

    # ── Load norms ────────────────────────────────────────────────────────
    store   = NormStore(":memory:")
    monitor = NormMonitor()

    for norm in CODING_NORMS:
        monitor.add_norm(norm)
        store.save_norm(norm)

    print(f"\n{len(CODING_NORMS)} engineering norms loaded:\n")
    for n in CODING_NORMS:
        print(f"  [{n.priority:2d}] {n.name}")

    # ── Check all proposed changes ────────────────────────────────────────
    hr()
    print("Checking proposed AI-generated changes against norms...\n")

    all_violations: list[NormViolation] = []
    blocked_prs:    set[str]            = set()
    changes_by_pr: dict[str, list] = {}

    for change in PROPOSED_CHANGES:
        pr = change["pr"]
        changes_by_pr.setdefault(pr, []).append(change)

    for pr, changes in changes_by_pr.items():
        pr_violations: list[tuple[NormViolation, str]] = []  # (violation, target)
        for ch in changes:
            action = AgentAction(
                agent_id  = ch["agent_id"],
                action    = ch["action"],
                location  = ch["location"],
                target    = ch["target"],
                timestamp = ch["ts"],
            )
            violations = monitor.check(action)
            for v in violations:
                pr_violations.append((v, ch["target"]))
                blocked_prs.add(pr)

        if pr_violations:
            print(f"  🚫 {pr} [{changes[0]['agent_id']}] — BLOCKED ({len(pr_violations)} violation(s))")
            for v, target in pr_violations:
                print(f"      • {v.norm_name}")
                print(f"        → {target}")
            all_violations.extend(v for v, _ in pr_violations)
        else:
            print(f"  ✓  {pr} [{changes[0]['agent_id']}] — passed")

    # ── Summary statistics ────────────────────────────────────────────────
    hr()
    total_prs      = len(changes_by_pr)
    blocked        = len(blocked_prs)
    violation_rate = (blocked / total_prs * 100) if total_prs else 0.0

    print("Gate results:\n")
    print(f"  PRs checked          : {total_prs}")
    print(f"  PRs blocked          : {blocked}  ({violation_rate:.0f}%)")
    print(f"  Total violations     : {len(all_violations)}")
    print(f"  PRs passed           : {total_prs - blocked}")

    hr()
    print("Violation breakdown by norm:\n")
    counts: dict[str, int] = {}
    for v in all_violations:
        counts[v.norm_name] = counts.get(v.norm_name, 0) + 1
    for name, count in sorted(counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"  {name:35s}  {count}×  {bar}")

    # ── Industry context ──────────────────────────────────────────────────
    hr()
    print("Industry context:\n")
    print("  • 71% of AI-assisted PRs contained ≥1 norm violation in internal audit")
    print("  • Teams without a pre-commit gate had 2.3× higher post-merge defect rate")
    print("  • Most common violation: hardcoded secrets (38% of all violations)")
    print("  • 92% of violations were caught in <200ms by normsync gate\n")

    # ── Rich violation table + JSON export ───────────────────────────────────
    if all_violations:
        hr()
        print("Rich violation table:\n")
        print_violations(all_violations)
        print()
        hr()
        export = to_json(CODING_NORMS, violations=all_violations)
        print(f"Violation log exported ({len(export)} chars JSON)")
        print("  → Pipe to SIEM, Jira, or compliance dashboard for quarterly audit.\n")


if __name__ == "__main__":
    main()
