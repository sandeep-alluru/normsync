# Closed loop — `normsync`

**Status:** reader wired (eagle-eyes / 2026-08-06) — **NORM-ENFORCE**  
**Owner loop:** L7 multi-agent

## Load-bearing job

Norm registry + violation monitoring + **action gate**

## Who reads the output?

- Library: `gate_action` / `assert_action_allowed` / `gate_actions`
- `NormMonitor.check` is used inside the gate; violations may be saved to store

## What outcome changes?

Prohibited actions blocked (FAIL). High-risk unattended actions with **zero**
active norms → **FAIL_LOUD** (NORM-ENFORCE / unattended post).

## When NOT to use (anti-ornament)

Write-only norm store without check path

## Non-Ornament checklist

- [x] Reader implemented (`closed_loop.gate_action`)
- [x] Empty/wrong output fails loudly (exit 2 for no norms on high-risk)
- [x] Not free MCP decoration without gate
- [ ] Linked gap IDs in mem0 when improving

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

This file exists so pillar **C (closed loop)** can rise with real wiring over time. Prefer small daily commits that move a checkbox toward done.

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2
