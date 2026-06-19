"""Detect conflicting norms."""
from __future__ import annotations

from dataclasses import dataclass

from normsync.store import NormStore


@dataclass
class NormConflict:
    norm_a: str     # norm name
    norm_b: str     # norm name
    conflict_type: str   # "logical_contradiction", "priority_ambiguity", "scope_overlap"
    description: str
    example_action: str   # an action that would trigger both norms


def _tokens(text: str) -> set[str]:
    """Return the set of non-empty lowercase tokens from a string."""
    return {t for t in text.lower().split() if t}


def detect_norm_conflicts(store: NormStore) -> list[NormConflict]:
    """Find norms that may contradict each other."""
    norms = store.get_norms(active_only=True)
    conflicts: list[NormConflict] = []
    # Track (pair, conflict_type) to avoid duplicates
    seen: set[tuple[frozenset[str], str]] = set()

    for i, norm_a in enumerate(norms):
        for norm_b in norms[i + 1:]:
            # Tokens for each norm's fields
            a_prohibited = _tokens(norm_a.prohibited)
            b_prohibited = _tokens(norm_b.prohibited)
            a_condition = _tokens(norm_a.condition)
            b_condition = _tokens(norm_b.condition)
            pair = frozenset([norm_a.name, norm_b.name])

            # 1. Logical contradiction:
            #    a's prohibited tokens appear in b's condition, or vice versa
            if a_prohibited & b_condition or b_prohibited & a_condition:
                ctype = "logical_contradiction"
                key = (pair, ctype)
                if key not in seen:
                    seen.add(key)
                    overlapping_tokens = (a_prohibited & b_condition) | (b_prohibited & a_condition)
                    example_tok = next(iter(overlapping_tokens))
                    all_cond_tokens = a_condition | b_condition
                    conflicts.append(NormConflict(
                        norm_a=norm_a.name,
                        norm_b=norm_b.name,
                        conflict_type=ctype,
                        description=(
                            f"Norm '{norm_a.name}' prohibits actions that norm '{norm_b.name}' "
                            f"requires by condition (or vice versa): conflicting token(s) "
                            f"{overlapping_tokens!r}"
                        ),
                        example_action=(
                            "action='{}' in condition='{}'".format(
                                example_tok, " ".join(sorted(all_cond_tokens))
                            )
                        ),
                    ))

            # 2. Priority ambiguity:
            #    same priority, same scope, overlapping condition tokens
            if (
                norm_a.priority == norm_b.priority
                and norm_a.scope == norm_b.scope
                and a_condition & b_condition
            ):
                ctype = "priority_ambiguity"
                key = (pair, ctype)
                if key not in seen:
                    seen.add(key)
                    shared_cond = a_condition & b_condition
                    example_tok = next(iter(shared_cond))
                    conflicts.append(NormConflict(
                        norm_a=norm_a.name,
                        norm_b=norm_b.name,
                        conflict_type=ctype,
                        description=(
                            f"Norms '{norm_a.name}' and '{norm_b.name}' share the same priority "
                            f"({norm_a.priority}) and scope ('{norm_a.scope}') with overlapping "
                            f"condition tokens {shared_cond!r} — resolution is ambiguous"
                        ),
                        example_action=(
                            "action='{}' in condition='{}'".format(
                                example_tok, " ".join(sorted(shared_cond))
                            )
                        ),
                    ))

            # 3. Scope overlap:
            #    one is "global", the other is more specific, AND they share condition tokens
            scopes = {norm_a.scope, norm_b.scope}
            if "global" in scopes and len(scopes) == 2 and a_condition & b_condition:
                ctype = "scope_overlap"
                key = (pair, ctype)
                if key not in seen:
                    seen.add(key)
                    shared_cond = a_condition & b_condition
                    specific_norm = norm_b if norm_a.scope == "global" else norm_a
                    global_norm = norm_a if norm_a.scope == "global" else norm_b
                    example_tok = next(iter(shared_cond))
                    conflicts.append(NormConflict(
                        norm_a=norm_a.name,
                        norm_b=norm_b.name,
                        conflict_type=ctype,
                        description=(
                            f"Global norm '{global_norm.name}' overlaps in condition with "
                            f"scope-specific norm '{specific_norm.name}' "
                            f"(scope='{specific_norm.scope}') "
                            f"on token(s) {shared_cond!r}"
                        ),
                        example_action=(
                            "action='{}' in condition='{}'".format(
                                example_tok, " ".join(sorted(shared_cond))
                            )
                        ),
                    ))

    return conflicts
