"""RULE-INTENSIVE / GB/T-Bench - hierarchical document review gate.

Public case (Track B 20260809T201218Z):
  arXiv 2608.06312 Benchmarking and Enhancing LLMs for Rule-Intensive Review
  of National Standard Documents. Reviewers that claim approve/complete without
  hierarchical taxonomy coverage (structure, scope, modality, terminology,
  cross-section) are ornament — gate refuses.
"""

from __future__ import annotations

import pytest

from normsync.closed_loop import (
    DEFAULT_RULE_REVIEW_DIMENSIONS,
    ClosedLoopError,
    analyze_rule_review,
    assert_rule_review_ok,
    gate_rule_review,
    is_rule_review_dimension,
)

FULL_TAXONOMY = sorted(DEFAULT_RULE_REVIEW_DIMENSIONS)


def test_default_taxonomy_has_five_dimensions() -> None:
    assert "document_structure" in DEFAULT_RULE_REVIEW_DIMENSIONS
    assert "scope_alignment" in DEFAULT_RULE_REVIEW_DIMENSIONS
    assert "normative_modality" in DEFAULT_RULE_REVIEW_DIMENSIONS
    assert "terminology_consistency" in DEFAULT_RULE_REVIEW_DIMENSIONS
    assert "cross_section_consistency" in DEFAULT_RULE_REVIEW_DIMENSIONS
    assert len(DEFAULT_RULE_REVIEW_DIMENSIONS) == 5


def test_is_rule_review_dimension() -> None:
    assert is_rule_review_dimension("terminology_consistency") is True
    assert is_rule_review_dimension("terminology") is True
    assert is_rule_review_dimension("unrelated_score") is False


def test_phantom_approve_zero_dimensions_fails_loud() -> None:
    """PRE-FIX class: claim approved with no hierarchical checks → FAIL_LOUD."""
    out = gate_rule_review(
        findings=[],
        dimensions_checked=[],
        claim_approved=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert "RULE-INTENSIVE" in out.reason or "GB-T" in out.reason
    assert out.covered_dimensions == ()


def test_complete_claim_without_taxonomy_fails_loud() -> None:
    out = gate_rule_review(claim_complete=True, dimensions_checked=None)
    assert out.verdict == "FAIL_LOUD"
    assert out.action == "complete_review"


def test_missing_taxonomy_dimension_fails() -> None:
    partial = [d for d in FULL_TAXONOMY if d != "terminology_consistency"]
    out = gate_rule_review(
        dimensions_checked=partial,
        claim_approved=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "terminology_consistency" in out.missing_dimensions
    assert out.violation_count >= 1
    payload = out.to_dict()
    assert "terminology_consistency" in payload["missing_dimensions"]


def test_unresolved_critical_finding_blocks_approve() -> None:
    findings = [
        {
            "id": "t1",
            "dimension": "terminology_consistency",
            "severity": "critical",
            "message": "term 'agent' defined twice inconsistently",
            "resolved": False,
        }
    ]
    out = gate_rule_review(
        findings,
        dimensions_checked=FULL_TAXONOMY,
        claim_approved=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.critical_finding_count == 1
    assert out.human_required is True


def test_resolved_critical_allows_approve() -> None:
    findings = [
        {
            "id": "t1",
            "dimension": "terminology_consistency",
            "severity": "critical",
            "message": "fixed",
            "resolved": True,
        }
    ]
    out = gate_rule_review(
        findings,
        dimensions_checked=FULL_TAXONOMY,
        claim_approved=True,
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.critical_finding_count == 0


def test_modality_shall_to_may_fails() -> None:
    findings = [
        {
            "id": "m1",
            "dimension": "normative_modality",
            "severity": "info",
            "expected_modality": "shall",
            "actual_modality": "may",
            "message": "requirement weakened to optional",
        }
    ]
    out = gate_rule_review(
        findings,
        dimensions_checked=FULL_TAXONOMY,
        claim_approved=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "modality" in out.reason.lower() or "RULE-INTENSIVE" in out.reason


def test_full_taxonomy_clean_approve_passes() -> None:
    out = gate_rule_review(
        findings=[],
        dimensions_checked=FULL_TAXONOMY,
        claim_approved=True,
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    assert set(out.covered_dimensions) == set(FULL_TAXONOMY)
    assert out.missing_dimensions == ()
    d = out.to_dict()
    assert d["ok"] is True
    assert len(d["covered_dimensions"]) == 5


def test_findings_contribute_covered_dimensions() -> None:
    """Coverage can be inferred from finding dimensions alone."""
    findings = [
        {"id": f"f{i}", "dimension": dim, "severity": "info", "resolved": True}
        for i, dim in enumerate(FULL_TAXONOMY)
    ]
    out = gate_rule_review(findings, claim_approved=True)
    assert out.ok is True
    assert set(out.covered_dimensions) == set(FULL_TAXONOMY)


def test_analyze_rule_review_summary() -> None:
    summary = analyze_rule_review(
        [{"dimension": "document_structure", "severity": "minor"}],
        dimensions_checked=["scope_alignment"],
    )
    assert "document_structure" in summary["covered_dimensions"]
    assert "scope_alignment" in summary["covered_dimensions"]
    assert "terminology_consistency" in summary["missing_dimensions"]
    assert summary["full_taxonomy"] is False


def test_assert_rule_review_ok_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_rule_review_ok(claim_approved=True, dimensions_checked=[])


def test_assert_rule_review_ok_passes() -> None:
    out = assert_rule_review_ok(
        dimensions_checked=FULL_TAXONOMY,
        claim_approved=True,
    )
    assert out.ok is True


def test_empty_non_claim_fails_loud() -> None:
    out = gate_rule_review()
    assert out.verdict == "FAIL_LOUD"


def test_partial_without_claim_fails_on_incomplete_taxonomy() -> None:
    out = gate_rule_review(
        dimensions_checked=["document_structure"],
        claim_approved=False,
        require_full_taxonomy=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert len(out.missing_dimensions) >= 1
