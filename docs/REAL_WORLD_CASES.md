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

## Case SCOPE-BOUND — MNC out-of-scope declassification

**Source:** Track B research (`20260808T001238Z`):

| Case | Link |
|------|------|
| MNC scope-bound declassification | arXiv [2608.01719](https://arxiv.org/abs/2608.01719v1) |
| Multi-agent private communication | agents share beyond declared channel scope |
| SocietyBench / ICLR multi-agent | norms must constrain coordination (prior) |

**What fails:**

1. Multi-agent channels declare a **scope** (team, private audience).
2. Agents `share` / `export` / `declassify` / `publish` content to targets
   **outside** that scope (or to `public` without a declassify grant).
3. `gate_action` alone checks norm registry presence, not **scope ⊆ declared**.

**Product in this repo:**

| Control | API |
|---------|-----|
| Cross-scope classifier | `is_cross_scope_action` / `DEFAULT_CROSS_SCOPE_ACTIONS` |
| Scope gate | `gate_scope(action, declared_scope=…, target_scope=…)` |
| Declassify grant | `allow_declassify=True` required to widen classification |
| Raise form | `assert_in_scope(...)` |

**Rules (load-bearing):**

- Empty declared scope → **FAIL_LOUD**
- target ∉ declared → **FAIL** (`out_of_scope`)
- declassify/reveal private without grant → **FAIL**
- private→public share without grant → **FAIL**

**Tests:** `tests/test_scope_bound.py`

**Non-Ornament:** Call `gate_scope` **before** any multi-agent share/export.
Pair with `gate_action` for high-risk empty-norm refuse and
`humanproof.gate_approval` for owner tokens.

---

## Case RULE-INTENSIVE — GB/T hierarchical document review

**Source:** Track B research (`20260809T201218Z`):

| Case | Link |
|------|------|
| Rule-intensive national standard review | arXiv [2608.06312](https://arxiv.org/abs/2608.06312v1) |
| GB/T-Bench hierarchical taxonomy | structure, scope, modality, terminology, cross-section |
| Domain Q&A-only evals | miss intrinsic quality review (paper gap) |

**What fails:**

1. LLM agents “review” long structured standards with only domain Q&A scores.
2. Reviewers claim **approved** / **complete** without hierarchical taxonomy
   coverage (document structure, scope alignment, normative modality,
   terminology consistency, cross-section consistency).
3. Unresolved critical findings or shall→may modality weakenings still ship
   as green review.
4. `gate_action` / `gate_scope` alone do not encode **document rule taxonomy**.

**Product in this repo:**

| Control | API |
|---------|-----|
| Taxonomy constants | `DEFAULT_RULE_REVIEW_DIMENSIONS`, `CRITICAL_REVIEW_SEVERITIES` |
| Analyzer | `analyze_rule_review(findings, dimensions_checked=…)` |
| Review gate | `gate_rule_review(..., claim_approved=…)` |
| Raise form | `assert_rule_review_ok(...)` |
| Dimension helper | `is_rule_review_dimension` |

**Rules (load-bearing):**

- claim approve/complete + zero dimensions checked → **FAIL_LOUD**
- missing required taxonomy dimensions → **FAIL**
- unresolved critical/major findings above budget → **FAIL**
- normative modality weakening (shall/must → may/should) → **FAIL**
- full taxonomy + no blockers → **PASS**

**Tests:** `tests/test_rule_intensive.py`

**Non-Ornament:** Call `gate_rule_review` **before** accepting a document
approve/complete decision. Pair with `gate_action` for side-effect norms and
`gate_scope` when review outputs are shared across agents.

## Related queue IDs

- **NORM-ENFORCE** — unattended post without norms
- **SCOPE-BOUND** — MNC declassification
- **RULE-INTENSIVE** — GB/T hierarchical review (this section)
- **APPROVAL-GATE** (humanproof) — owner token for high-risk
- **CONST-AS-STATE** (agentcrdt) — refuse non-world state
- **POLICY-ARBITRATION** (rulegraph) — COI / endorse rules
- **MAST-MULTI** (agentcrdt) — multi-agent silent divergence
