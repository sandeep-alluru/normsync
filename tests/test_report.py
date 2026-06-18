"""Tests for report formatters."""
from __future__ import annotations

import io
import json

from rich.console import Console

from normsync.norm import NormViolation, WorldNorm
from normsync.report import print_violations, to_json, to_markdown


def make_norms() -> list[WorldNorm]:
    return [
        WorldNorm("no-attack", "No attacking", "safe_zone", "attack"),
        WorldNorm("no-steal", "No stealing", "market", "steal", active=False),
    ]


def make_violations() -> list[NormViolation]:
    return [
        NormViolation(
            "norm1", "no-attack", "act1", "agent1", "Violated no-attack", timestamp=1.0
        ),
    ]


class TestToJson:
    def test_returns_valid_json(self):
        norms = make_norms()
        result = to_json(norms)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_has_norm_count(self):
        norms = make_norms()
        data = json.loads(to_json(norms))
        assert data["norm_count"] == 2

    def test_has_active_count(self):
        norms = make_norms()
        data = json.loads(to_json(norms))
        assert data["active_count"] == 1

    def test_with_violations_has_has_violations(self):
        norms = make_norms()
        violations = make_violations()
        data = json.loads(to_json(norms, violations))
        assert data["has_violations"] is True
        assert data["violation_count"] == 1

    def test_without_violations_no_violations_key(self):
        norms = make_norms()
        data = json.loads(to_json(norms))
        assert "violations" not in data

    def test_empty_violations_has_violations_false(self):
        norms = make_norms()
        data = json.loads(to_json(norms, []))
        assert data["has_violations"] is False


class TestToMarkdown:
    def test_returns_string(self):
        norms = make_norms()
        result = to_markdown(norms)
        assert isinstance(result, str)

    def test_has_table_chars(self):
        norms = make_norms()
        result = to_markdown(norms)
        assert "|" in result

    def test_includes_norm_names(self):
        norms = make_norms()
        result = to_markdown(norms)
        assert "no-attack" in result

    def test_includes_violations(self):
        norms = make_norms()
        violations = make_violations()
        result = to_markdown(norms, violations)
        assert "agent1" in result

    def test_active_count_in_output(self):
        norms = make_norms()
        result = to_markdown(norms)
        assert "1" in result  # 1 active norm


class TestPrintViolations:
    def test_outputs_text(self):
        violations = make_violations()
        buf = io.StringIO()
        con = Console(file=buf, highlight=False)
        print_violations(violations, console=con)
        output = buf.getvalue()
        assert len(output) > 0

    def test_no_violations_prints_no_violations(self):
        buf = io.StringIO()
        con = Console(file=buf, highlight=False)
        print_violations([], console=con)
        output = buf.getvalue()
        assert "No violations" in output

    def test_includes_agent_id(self):
        violations = make_violations()
        buf = io.StringIO()
        con = Console(file=buf, highlight=False)
        print_violations(violations, console=con)
        output = buf.getvalue()
        assert "agent1" in output
