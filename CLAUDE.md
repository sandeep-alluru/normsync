# normsync — Session Anchor

**Research spec:** `../tech-research/14-Gaming/social-contract-enforcement-engine-binding-multi-agent-n/README.md`  
**One-liner:** Emergent norm enforcement for multi-agent worlds — signed CRDT commitment ledger  
**Phase:** backlog  
**Stack:** Python, automerge-py (or py-crdt), cryptography, anthropic (Claude API)  

## Key decisions
- Key architectural separation: LLM decides WHAT norms exist; deterministic engine decides enforcement
<!-- more decisions as sessions progress -->

## Next step
Read the research spec, then design the signed commitment ledger schema.

## MVP definition
- `pip install normsync` works
- Signed, versioned, append-only CRDT commitment ledger
- Tool-call interface: agents propose norms, accept norms, query active norms
- Deterministic enforcement engine (no LLM in the enforcement path)
- Demo: two NPC agents negotiate "don't attack allies" norm; third agent violates it; enforcement fires
- API: `normsync.propose(norm)`, `normsync.accept(norm_id)`, `normsync.enforce(action)`
- README with clear architecture diagram showing LLM vs deterministic boundary
