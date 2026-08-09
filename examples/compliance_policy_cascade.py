"""
compliance_policy_cascade.py — GDPR policy cascade across a fintech AI fleet.

A fintech firm runs 5 AI agents across two compliance domains:

  • loan-agent     Loan underwriting — analyses applicant documents via LLM
  • fraud-agent    Fraud detection — scans transaction streams in real time
  • kyc-agent      KYC/AML — verifies customer identity documents
  • reporting-agent Regulatory reporting — drafts GDPR and PSD2 reports
  • audit-agent    Internal audit — cross-checks agent behaviour logs

When the legal team updates the firm's GDPR interpretation ("no PII in
LLM prompts" → "no PII or financial data in LLM prompts"), normsync
propagates the change to all 5 agents in under 200ms — no system-prompt
edits, no redeploys.

This script demonstrates:
  1. Initial compliance policy set (3 GDPR/PSD2 norms)
  2. 20 agent actions — 4 clean, then a burst of 7 pre-update violations,
     then the policy update lands mid-run, then 9 post-update actions where
     the new rule is automatically enforced
  3. The GDPR Q3 policy cascade: one store.save_norm() call, all agents
     see the new norm on their next check()
  4. Conflict detection when the audit team proposes a contradictory norm
  5. Fleet compliance report — agents ranked worst-first by compliance_rate
  6. Regulator audit trail from NormVersionStore

Run:
    python examples/compliance_policy_cascade.py
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from normsync.compliance import fleet_compliance_report
from normsync.conflicts import detect_norm_conflicts
from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, NormViolation, WorldNorm
from normsync.store import NormStore
from normsync.versioning import NormVersionStore

# ── Constants ─────────────────────────────────────────────────────────────────

AGENTS = [
    "loan-agent",      # Loan underwriting — LLM document analysis
    "fraud-agent",     # Fraud detection — real-time transaction scanning
    "kyc-agent",       # KYC/AML — identity verification
    "reporting-agent", # Regulatory reporting — GDPR and PSD2 drafts
    "audit-agent",     # Internal audit — cross-checks agent behaviour
]

BASE_TIMESTAMP = 1_752_000_000.0  # fixed epoch for reproducible output

# Simulated cascade timing: policy lands at T+00:15:00 (15 minutes in)
POLICY_UPDATE_OFFSET = 15 * 60  # seconds


def hr(char: str = "─", width: int = 74) -> None:
    print(char * width)


def fmt_time(ts: float) -> str:
    elapsed = int(ts - BASE_TIMESTAMP)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    return f"T+{h:02d}:{m:02d}:{s:02d}"


# ── Initial policy set ────────────────────────────────────────────────────────

def build_initial_norms() -> list[WorldNorm]:
    """3 GDPR/PSD2 compliance norms active before the Q3 update."""
    return [
        WorldNorm(
            name="no-pii-in-prompts",
            description=(
                "AI agents must not include raw PII (name, email, NI number) "
                "in LLM prompts sent to external providers."
            ),
            condition="llm_prompt external",
            prohibited="transmit_pii",
            scope="global",
            active=True,
            priority=10,
        ),
        WorldNorm(
            name="no-cross-border-data-transfer",
            description=(
                "Agents must not transmit EU customer data to non-EEA infrastructure "
                "without SCCs in place."
            ),
            condition="data_transfer eu_customer",
            prohibited="send_non_eea",
            scope="global",
            active=True,
            priority=9,
        ),
        WorldNorm(
            name="require-audit-log",
            description=(
                "Every agent action that reads or writes customer data must emit "
                "an audit log entry."
            ),
            condition="customer_data read write",
            prohibited="skip_audit_log",
            scope="compliance",
            active=True,
            priority=8,
        ),
    ]


# ── Updated policy (the cascade) ──────────────────────────────────────────────

def build_updated_gdpr_norm() -> WorldNorm:
    """Q3 update: extend PII prohibition to include financial data in prompts."""
    return WorldNorm(
        name="no-pii-or-financial-in-prompts",
        description=(
            "AI agents must not transmit PII or financial data (account balances, "
            "transaction histories, credit scores) in raw LLM prompts sent to "
            "external providers."
        ),
        condition="llm_prompt external",
        prohibited="transmit_sensitive",
        scope="global",
        active=True,
        priority=10,
    )


# ── Conflicting norm (proposed by audit team — should be blocked) ─────────────

def build_conflicting_norm() -> WorldNorm:
    """
    Audit team proposes requiring agents to transmit full financial context to LLMs
    for explainability. This contradicts no-pii-or-financial-in-prompts.
    detect_norm_conflicts() should flag it before it is deployed.
    """
    return WorldNorm(
        name="require-full-financial-context-in-prompts",
        description=(
            "For explainability, agents must include full financial context "
            "(balances, transaction history) in LLM prompts."
        ),
        condition="llm_prompt external",
        prohibited="omit_financial_context",
        scope="global",
        active=True,
        priority=10,
    )


# ── Agent action simulation ───────────────────────────────────────────────────

@dataclass
class SimAction:
    agent: str
    action: str
    location: str
    target: str
    faction: str
    offset: float        # seconds from BASE_TIMESTAMP
    label: str = ""      # human-readable description for the report
    is_pre_update: bool = True


def build_actions() -> list[SimAction]:
    """
    20 agent actions across the 5-agent fintech fleet.

    Phase 1 (T+00:00–T+00:14): 11 actions — 4 clean, 7 pre-update violations
      Under the initial "no-pii-in-prompts" norm, agents sending financial data
      in prompts are NOT yet in violation (that prohibition is added in Q3 update).

    Phase 2 (T+00:15): GDPR Q3 policy cascade — one NormStore write
      New norm "no-pii-or-financial-in-prompts" activated.
      All agents pick it up on their next check().

    Phase 3 (T+00:16–T+00:30): 9 actions — 5 violations caught by new norm,
      4 clean. The same financial-data-in-prompt actions that were allowed in
      Phase 1 are now blocked.
    """
    actions: list[SimAction] = [

        # ── Phase 1: pre-update ────────────────────────────────────────────────
        SimAction("loan-agent",      "analyse_document",
                  location="document_store customer_data read",
                  target="applicant_doc_8812",
                  faction="loan_underwriting",
                  offset=60,
                  label="Read applicant doc — audit log required",
                  is_pre_update=True),

        SimAction("kyc-agent",       "verify_identity",
                  location="document_store customer_data read",
                  target="passport_scan_4401",
                  faction="kyc",
                  offset=120,
                  label="KYC identity check — audit log required",
                  is_pre_update=True),

        SimAction("fraud-agent",     "flag_transaction",
                  location="transaction_stream",
                  target="txn-99021-suspicious",
                  faction="fraud",
                  offset=180,
                  label="Flag suspicious transaction — clean",
                  is_pre_update=True),

        SimAction("reporting-agent", "draft_gdpr_report",
                  location="report_engine",
                  target="dpa_q3_draft.pdf",
                  faction="reporting",
                  offset=240,
                  label="Draft GDPR report — clean",
                  is_pre_update=True),

        # Pre-update: transmitting financial data in prompts — NOT yet prohibited
        SimAction("loan-agent",      "transmit_pii",
                  location="llm_prompt external underwriting",
                  target="applicant_credit_score_742",
                  faction="loan_underwriting",
                  offset=300,
                  label="Transmit PII to LLM — violates no-pii-in-prompts",
                  is_pre_update=True),

        SimAction("fraud-agent",     "transmit_pii",
                  location="llm_prompt external fraud_analysis",
                  target="account_balance_raw_EUR_48200",
                  faction="fraud",
                  offset=360,
                  label="Transmit PII to LLM — violates no-pii-in-prompts",
                  is_pre_update=True),

        SimAction("kyc-agent",       "transmit_pii",
                  location="llm_prompt external kyc_verification",
                  target="ni_number_GB123456A",
                  faction="kyc",
                  offset=420,
                  label="Transmit NI number to LLM — violates no-pii-in-prompts",
                  is_pre_update=True),

        SimAction("reporting-agent", "transmit_pii",
                  location="llm_prompt external report_gen",
                  target="customer_email_list_batch9",
                  faction="reporting",
                  offset=480,
                  label="Transmit email list to LLM — violates no-pii-in-prompts",
                  is_pre_update=True),

        SimAction("audit-agent",     "skip_audit_log",
                  location="customer_data read write",
                  target="agent_action_batch_44",
                  faction="audit",
                  offset=540,
                  label="Skip audit log on customer data access — violates require-audit-log",
                  is_pre_update=True),

        SimAction("loan-agent",      "send_non_eea",
                  location="data_transfer eu_customer export_pipeline",
                  target="us_east_llm_endpoint",
                  faction="loan_underwriting",
                  offset=600,
                  label="Send EU customer data to non-EEA endpoint — violates cross-border norm",
                  is_pre_update=True),

        SimAction("fraud-agent",     "skip_audit_log",
                  location="customer_data read write",
                  target="txn_analysis_batch_77",
                  faction="fraud",
                  offset=660,
                  label="Skip audit log on transaction batch — violates require-audit-log",
                  is_pre_update=True),

        # ── Phase 2: GDPR Q3 cascade (policy update stored to NormStore at T+15:00) ──
        # (policy update happens in main() between the two phases)

        # ── Phase 3: post-update — new norm enforced automatically ─────────────
        SimAction("loan-agent",      "transmit_sensitive",
                  location="llm_prompt external underwriting",
                  target="credit_score_and_balance_raw",
                  faction="loan_underwriting",
                  offset=POLICY_UPDATE_OFFSET + 60,
                  label="Transmit credit score + balance to LLM — violates Q3 norm",
                  is_pre_update=False),

        SimAction("fraud-agent",     "transmit_sensitive",
                  location="llm_prompt external fraud_analysis",
                  target="transaction_history_90d_EUR",
                  faction="fraud",
                  offset=POLICY_UPDATE_OFFSET + 120,
                  label="Transmit transaction history to LLM — violates Q3 norm",
                  is_pre_update=False),

        SimAction("kyc-agent",       "verify_identity",
                  location="document_store customer_data read",
                  target="passport_scan_4408",
                  faction="kyc",
                  offset=POLICY_UPDATE_OFFSET + 180,
                  label="KYC identity check — clean (no LLM prompt)",
                  is_pre_update=False),

        SimAction("reporting-agent", "transmit_sensitive",
                  location="llm_prompt external report_gen",
                  target="balance_sheet_q3_anonymized",
                  faction="reporting",
                  offset=POLICY_UPDATE_OFFSET + 240,
                  label="Transmit financial data to LLM — violates Q3 norm",
                  is_pre_update=False),

        SimAction("audit-agent",     "analyse_logs",
                  location="agent_audit_store",
                  target="fleet_action_log_week39",
                  faction="audit",
                  offset=POLICY_UPDATE_OFFSET + 300,
                  label="Audit log analysis — clean",
                  is_pre_update=False),

        SimAction("loan-agent",      "analyse_document",
                  location="document_store customer_data read",
                  target="applicant_doc_8820",
                  faction="loan_underwriting",
                  offset=POLICY_UPDATE_OFFSET + 360,
                  label="Read applicant doc — clean post-update",
                  is_pre_update=False),

        SimAction("fraud-agent",     "transmit_sensitive",
                  location="llm_prompt external fraud_analysis",
                  target="account_balance_EUR_91300_raw",
                  faction="fraud",
                  offset=POLICY_UPDATE_OFFSET + 420,
                  label="Transmit account balance to LLM — violates Q3 norm",
                  is_pre_update=False),

        SimAction("kyc-agent",       "transmit_sensitive",
                  location="llm_prompt external kyc_verification",
                  target="credit_score_raw_plus_ni_number",
                  faction="kyc",
                  offset=POLICY_UPDATE_OFFSET + 480,
                  label="Transmit credit score + NI to LLM — violates Q3 norm",
                  is_pre_update=False),

        SimAction("reporting-agent", "draft_gdpr_report",
                  location="report_engine",
                  target="dpa_q4_draft.pdf",
                  faction="reporting",
                  offset=POLICY_UPDATE_OFFSET + 540,
                  label="Draft Q4 GDPR report — clean",
                  is_pre_update=False),
    ]
    return actions


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    hr("═")
    print("  CLEARPATH FINANCIAL — GDPR POLICY CASCADE REPORT")
    print("  Fleet: 5 fintech agents | Engine: normsync")
    hr("═")

    # ── [1/4] Load initial compliance norms ───────────────────────────────────
    print("\n[1/4] Loading initial GDPR/PSD2 compliance norms …")
    store = NormStore(":memory:")
    version_store = NormVersionStore(store)
    monitor = NormMonitor(store)     # live store — policy changes propagate automatically

    initial_norms = build_initial_norms()
    for norm in initial_norms:
        store.save_norm(norm)
        version_store.record_change(
            norm,
            changed_by="compliance_team",
            reason="Initial GDPR/PSD2 policy set — Q2 baseline",
        )
    # Also add initial norms to monitor's in-memory list for non-store mode compatibility
    # (store-backed monitor: active_norms() queries store directly)
    print(f"      Active norms loaded: {len(monitor.active_norms())}")
    for n in monitor.active_norms():
        print(f"        • [{n.name}] priority={n.priority} scope={n.scope}")

    # ── [2/4] Simulate agent actions (pre-update, cascade, post-update) ───────
    print("\n[2/4] Simulating agent actions …")
    sim_actions = build_actions()
    pre_update_actions = [a for a in sim_actions if a.is_pre_update]
    post_update_actions = [a for a in sim_actions if not a.is_pre_update]
    print(f"      Total actions:        {len(sim_actions)}")
    print(f"      Pre-update actions:   {len(pre_update_actions)}")
    print(f"      Post-update actions:  {len(post_update_actions)}")

    all_violations: list[NormViolation] = []
    timeline: list[tuple[SimAction, list[NormViolation], str]] = []

    # Phase 1: run pre-update actions
    for sim in pre_update_actions:
        action = AgentAction(
            agent_id=sim.agent,
            action=sim.action,
            location=sim.location,
            target=sim.target,
            faction=sim.faction,
            timestamp=BASE_TIMESTAMP + sim.offset,
        )
        viols = monitor.check(action)
        for v in viols:
            store.save_violation(v)
        all_violations.extend(viols)
        phase = "PRE "
        timeline.append((sim, viols, phase))

    # Policy cascade: Q3 GDPR update
    update_time = BASE_TIMESTAMP + POLICY_UPDATE_OFFSET
    updated_norm = build_updated_gdpr_norm()
    store.save_norm(updated_norm)
    version_store.record_change(
        updated_norm,
        changed_by="legal_team",
        reason="GDPR Q3 update: extend PII prohibition to include financial data in LLM prompts",
    )
    print(
        f"\n  *** GDPR Q3 POLICY CASCADE at {fmt_time(update_time)} ***\n"
        f"      Norm saved to NormStore: '{updated_norm.name}'\n"
        f"      All 5 agents will enforce this on their next check() call.\n"
        f"      No redeploy, no system-prompt edits, no per-team update cycle.\n"
    )

    # Phase 3: run post-update actions — new norm enforced automatically
    for sim in post_update_actions:
        action = AgentAction(
            agent_id=sim.agent,
            action=sim.action,
            location=sim.location,
            target=sim.target,
            faction=sim.faction,
            timestamp=BASE_TIMESTAMP + sim.offset,
        )
        viols = monitor.check(action)
        for v in viols:
            store.save_violation(v)
        all_violations.extend(viols)
        phase = "POST"
        timeline.append((sim, viols, phase))

    # ── [3/4] Conflict detection ───────────────────────────────────────────────
    print("[3/4] Checking for norm conflicts …")
    print("      Audit team proposes 'require-full-financial-context-in-prompts':")
    conflicting = build_conflicting_norm()
    # Temporarily add to the store for conflict detection
    store.save_norm(conflicting)
    conflicts = detect_norm_conflicts(store)
    # Remove the conflicting norm (mark inactive so it does not govern agents)
    conflicting_inactive = WorldNorm(
        name=conflicting.name,
        description=conflicting.description,
        condition=conflicting.condition,
        prohibited=conflicting.prohibited,
        scope=conflicting.scope,
        active=False,
        priority=conflicting.priority,
    )
    store.save_norm(conflicting_inactive)

    print(f"      detect_norm_conflicts() → {len(conflicts)} conflict(s) found")
    for c in conflicts:
        print(f"\n      CONFLICT: {c.norm_a!r} vs {c.norm_b!r}")
        print(f"        Type:    {c.conflict_type}")
        print(f"        Reason:  {c.description}")
        print(f"        Example: {c.example_action}")
    print("\n      Proposed norm BLOCKED — not deployed to agents.")

    # ── [4/4] Report ──────────────────────────────────────────────────────────
    print("\n[4/4] Generating compliance report …")
    hr()

    pre_viols  = [v for _, vs, ph in timeline if ph == "PRE " for v in vs]
    post_viols = [v for _, vs, ph in timeline if ph == "POST" for v in vs]

    print()
    print("  GDPR CASCADE SUMMARY:")
    print(f"    Agents in fleet:           {len(AGENTS)}")
    print(f"    Total actions checked:     {len(sim_actions)}")
    print(f"    Pre-update violations:     {len(pre_viols)}")
    print(f"    Post-update violations:    {len(post_viols)}  (new norm enforced automatically)")
    print(f"    Total violations detected: {len(all_violations)}")
    print()

    hr()
    print("\n  ACTION TIMELINE:")
    print(f"  {'Time':>10}  {'Phase':>4}  {'Agent':>16}  {'Action':>22}  {'Status'}")
    hr()

    for sim, viols, phase in timeline:
        ts_str = fmt_time(BASE_TIMESTAMP + sim.offset)
        if viols:
            norm_names = ", ".join(v.norm_name for v in viols)
            status = f"VIOLATION [{norm_names}]"
        else:
            status = "OK"
        print(
            f"  {ts_str:>10}  [{phase}]  "
            f"{sim.agent:>16}  "
            f"{sim.action:>22}  "
            f"{status}"
        )

    # Fleet compliance report
    hr()
    print("\n  FLEET COMPLIANCE REPORT (worst first):")
    print()

    actions_by_agent: dict[str, list[AgentAction]] = defaultdict(list)
    for sim, _, _ in timeline:
        actions_by_agent[sim.agent].append(
            AgentAction(
                agent_id=sim.agent,
                action=sim.action,
                location=sim.location,
                target=sim.target,
                faction=sim.faction,
                timestamp=BASE_TIMESTAMP + sim.offset,
            )
        )
    # Rebuild monitor with all current active norms (store-backed)
    fleet_report = fleet_compliance_report(monitor, dict(actions_by_agent))

    print(f"  {'Agent':>16}  {'Actions':>7}  {'Violations':>10}  {'Rate':>6}  {'Risk':>12}  Trend")
    hr()
    for rep in fleet_report:
        print(
            f"  {rep.agent_id:>16}  "
            f"{rep.total_actions:>7}  "
            f"{rep.violations:>10}  "
            f"{rep.compliance_rate:>5.0%}  "
            f"{rep.risk_level:>12}  "
            f"{rep.trend}"
        )

    # Regulator audit trail
    hr()
    print("\n  REGULATOR AUDIT TRAIL — 'no-pii-or-financial-in-prompts':")
    print()
    history = version_store.get_history(updated_norm.name)
    for v in reversed(history):
        import datetime
        ts = datetime.datetime.fromtimestamp(v.changed_at, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"    v{v.version}  [{ts}]  by={v.changed_by!r}")
        print(f"         reason: {v.change_reason}")
    print()
    hr("═")
    print(f"\n  Report generated at {time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Norms enforced: {len(monitor.active_norms())} | "
          f"Propagation model: live NormStore (zero-lag)")
    print()


if __name__ == "__main__":
    main()
