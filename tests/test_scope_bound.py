"""SCOPE-BOUND / MNC — out-of-scope declassification & export.

Public case (Track B 20260808T001238Z):
  arXiv 2608.01719 MNC: Scope-Bound Semantic Declassification for Private
  LLM-Agent Communication. Agents must not share/export private channel
  content outside declared scope without an explicit declassify grant.
"""

from __future__ import annotations

import pytest

from normsync.closed_loop import (
    ClosedLoopError,
    assert_in_scope,
    gate_scope,
    is_cross_scope_action,
)


def test_is_cross_scope_action() -> None:
    assert is_cross_scope_action("export") is True
    assert is_cross_scope_action("share") is True
    assert is_cross_scope_action("declassify") is True
    assert is_cross_scope_action("read") is False


def test_empty_declared_scope_fails_loud() -> None:
    out = gate_scope("share", declared_scope=[], target_scope=["team_a"])
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert "SCOPE-BOUND" in out.reason or "MNC" in out.reason


def test_empty_action_fails_loud() -> None:
    out = gate_scope("", declared_scope=["team_a"])
    assert out.verdict == "FAIL_LOUD"


def test_in_scope_share_passes() -> None:
    out = gate_scope(
        "share",
        declared_scope=["team_a", "team_b"],
        target_scope=["team_a"],
        classification="private",
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.out_of_scope == ()
    payload = out.to_dict()
    assert payload["declared_scope"] == ["team_a", "team_b"]


def test_out_of_scope_target_fails() -> None:
    out = gate_scope(
        "export",
        declared_scope=["team_a"],
        target_scope=["team_a", "external_vendor"],
        classification="private",
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "external_vendor" in out.out_of_scope
    assert out.human_required is True


def test_declassify_private_without_grant_fails() -> None:
    out = gate_scope(
        "declassify",
        declared_scope=["team_a"],
        target_scope=["team_a"],
        classification="private",
        allow_declassify=False,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "declassif" in out.reason.lower() or "MNC" in out.reason


def test_declassify_with_grant_passes() -> None:
    out = gate_scope(
        "declassify",
        declared_scope=["team_a", "public"],
        target_scope=["public"],
        classification="private",
        allow_declassify=True,
    )
    assert out.ok is True


def test_private_to_public_share_without_grant_fails() -> None:
    out = gate_scope(
        "share",
        declared_scope=["team_a", "public"],
        target_scope=["public"],
        classification="secret",
        allow_declassify=False,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_assert_in_scope_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_in_scope(
            "export",
            declared_scope=["internal"],
            target_scope=["internet"],
        )


def test_assert_in_scope_passes() -> None:
    out = assert_in_scope(
        "send",
        declared_scope=["alice", "bob"],
        target_scope=["bob"],
        classification="internal",
    )
    assert out.ok is True
