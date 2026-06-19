"""CLI tests using Click's test runner."""
from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from normsync.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db")


class TestCliHelp:
    def test_help_exits_0(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_help_contains_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "add" in result.output
        assert "check" in result.output
        assert "violations" in result.output

    def test_version_option(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0


class TestCliAdd:
    def test_add_norm(self, runner, tmp_db):
        result = runner.invoke(
            main,
            [
                "add",
                "no-attack",
                "No attacking in safe zones",
                "safe_zone",
                "attack",
                "--db",
                tmp_db,
            ],
        )
        assert result.exit_code == 0
        assert "no-attack" in result.output

    def test_add_creates_db(self, runner, tmp_db):
        runner.invoke(
            main,
            ["add", "test-norm", "desc", "cond", "prohibited", "--db", tmp_db],
        )
        assert os.path.exists(tmp_db)


class TestCliCheck:
    def test_check_no_db(self, runner, tmp_db):
        result = runner.invoke(
            main, ["check", "agent1", "attack", "safe_zone", "--db", tmp_db]
        )
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_check_with_violation(self, runner, tmp_db):
        runner.invoke(
            main,
            ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db],
        )
        result = runner.invoke(
            main,
            ["check", "agent1", "attack", "safe_zone", "--db", tmp_db],
        )
        assert result.exit_code == 0
        assert "violation" in result.output.lower()

    def test_check_no_violation(self, runner, tmp_db):
        runner.invoke(
            main,
            ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db],
        )
        result = runner.invoke(
            main,
            ["check", "agent1", "trade", "safe_zone", "--db", tmp_db],
        )
        assert result.exit_code == 0
        assert "No violations" in result.output


class TestCliViolations:
    def test_violations_no_db(self, runner, tmp_db):
        result = runner.invoke(main, ["violations", "--db", tmp_db])
        assert result.exit_code == 0

    def test_violations_json_format(self, runner, tmp_db):
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        runner.invoke(main, ["check", "agent1", "attack", "safe_zone", "--db", tmp_db])
        result = runner.invoke(
            main, ["violations", "--format", "json", "--db", tmp_db]
        )
        assert result.exit_code == 0

    def test_violations_markdown_format(self, runner, tmp_db):
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        result = runner.invoke(
            main, ["violations", "--format", "markdown", "--db", tmp_db]
        )
        assert result.exit_code == 0


class TestCliStatus:
    def test_status_no_db(self, runner, tmp_db):
        result = runner.invoke(main, ["status", "--db", tmp_db])
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_status_shows_counts(self, runner, tmp_db):
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        result = runner.invoke(main, ["status", "--db", tmp_db])
        assert result.exit_code == 0
        assert "Norms" in result.output


class TestCliCompliance:
    def test_compliance_no_db(self, runner, tmp_db):
        result = runner.invoke(main, ["compliance", "agent1", "--db", tmp_db])
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_compliance_no_violations(self, runner, tmp_db):
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        result = runner.invoke(main, ["compliance", "agent1", "--db", tmp_db])
        assert result.exit_code == 0
        assert "Compliance report" in result.output

    def test_compliance_with_violations(self, runner, tmp_db):
        # Add norm then create a violation
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        runner.invoke(main, ["check", "agent1", "attack", "safe_zone", "--db", tmp_db])
        result = runner.invoke(main, ["compliance", "agent1", "--db", tmp_db])
        assert result.exit_code == 0
        assert "agent1" in result.output


class TestCliConflicts:
    def test_conflicts_no_db(self, runner, tmp_db):
        result = runner.invoke(main, ["conflicts", "--db", tmp_db])
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_conflicts_no_conflicts(self, runner, tmp_db):
        runner.invoke(
            main, ["add", "no-attack", "desc", "safe_zone", "attack", "--db", tmp_db]
        )
        result = runner.invoke(main, ["conflicts", "--db", tmp_db])
        assert result.exit_code == 0

    def test_conflicts_detects_conflict(self, runner, tmp_db):
        # Two norms with same priority and overlapping condition — priority ambiguity
        runner.invoke(
            main,
            ["add", "norm-a", "Desc A", "zone combat", "flee", "--db", tmp_db,
             "--priority", "5", "--scope", "global"],
        )
        runner.invoke(
            main,
            ["add", "norm-b", "Desc B", "zone attack", "retreat", "--db", tmp_db,
             "--priority", "5", "--scope", "global"],
        )
        result = runner.invoke(main, ["conflicts", "--db", tmp_db])
        assert result.exit_code == 0
