# Real-world cases driving normsync

Mined from farm queue (eagle-eyes) and public multi-agent research (Track B).

## Case NORM-ENFORCE (farm) — CRITICAL

**Source:** eagle-eyes `REAL_WORK_QUEUE` P2 — *unattended post without norm*;
CLOSED_LOOP: write-only norm store without check path is ornament.

**What failed:**

1. Agents / cron publish (**post**, **auto_post**) with a norm registry that is
   never consulted — store exists, gate does not.
2. Unattended high-risk side effects proceed as if “no norms” meant “allowed.”
3. Related: X-lane FULL AUTO-POST flag removed HITL; without a norm gate the
   product has no load-bearing reader (see humanproof APPROVAL-GATE twin).

**Public twins:**

| Case | Mapping |
|------|---------|
| ICLR multi-agent failures / AgentPulse | Shared norms must constrain actions |
| FedCritic / History Matters / multi-agent planning | Coordination state + norms |
| SocietyBench (arXiv 2608.04009) | Social-world norms on agent acts |
| Guardian / AgentWatch | Runtime refuse without policy |

**Product fix in this repo:**

| Control | API |
|---------|-----|
| Action gate | `gate_action(action, norms)` |
| High-risk set | `post`, `publish`, `auto_post`, … (`is_high_risk_action`) |
| Empty norms + high-risk | `FAIL_LOUD` (exit 2) — NORM-ENFORCE |
| Violations | `FAIL` (exit 1) via `NormMonitor.check` |
| Batch | `gate_actions([...])` |
| Raise form | `assert_action_allowed(...)` |

**Tests:** `tests/test_gate_action.py`

**Non-Ornament:** Call `gate_action` **before** side effects. A filled
`NormStore` without a gate is still ornament.

---

## Related queue IDs

- **NORM-ENFORCE** — this case (P2)
- **APPROVAL-GATE** (humanproof) — owner token for high-risk
- **CONST-AS-STATE** (agentcrdt) — refuse non-world state
- **POLICY-ARBITRATION** (rulegraph) — COI / endorse rules
