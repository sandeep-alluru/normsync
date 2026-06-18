"""
End-to-end smoke test for normsync.

Simulates a user who just cloned the repo and wants to verify everything works.
No mocking, no fixtures — real behaviour, real CLI, real HTTP server.

Run from repo root:
    python smoke_test.py
    python smoke_test.py --verbose

Exit 0 = all passed. Exit 1 = at least one failure.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
REPO_ROOT = Path(__file__).parent
PYTHON = sys.executable

passed: list[str] = []
failed: list[tuple[str, str]] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  {GREEN}✓{RESET} {name}")


def fail(name: str, reason: str) -> None:
    failed.append((name, reason))
    print(f"  {RED}✗{RESET} {name}")
    if VERBOSE:
        print(f"    {YELLOW}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def run(name: str, fn):  # noqa: ANN001
    try:
        fn()
        ok(name)
    except Exception as exc:
        reason = str(exc) if not VERBOSE else traceback.format_exc().strip()
        fail(name, reason)


# ── 1. Package import ─────────────────────────────────────────────────────────

section("1. Package import")

def _test_import_version():
    import normsync
    assert normsync.__version__, "__version__ is empty"
    assert normsync.__version__ != "0.0.0"

def _test_import_public_api():
    # TODO: replace with your package's actual public API
    mod = importlib.import_module("normsync")
    assert mod is not None

run("normsync package imports", _test_import_version)
run("Public API importable", _test_import_public_api)


# ── 2. Core data model ────────────────────────────────────────────────────────

section("2. Core data model")

def _test_world_norm_content_addressing():
    from normsync.norm import WorldNorm
    n1 = WorldNorm("no-attack", "desc1", "safe_zone", "attack")
    n2 = WorldNorm("no-attack", "desc2", "safe_zone", "attack")
    assert n1.id == n2.id, f"Same inputs must produce same id: {n1.id} != {n2.id}"
    assert len(n1.id) == 16

def _test_world_norm_different_inputs_different_id():
    from normsync.norm import WorldNorm
    n1 = WorldNorm("no-attack", "desc", "safe_zone", "attack")
    n2 = WorldNorm("no-steal", "desc", "market", "steal")
    assert n1.id != n2.id

def _test_agent_action_content_addressing():
    from normsync.norm import AgentAction
    a1 = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
    a2 = AgentAction("agent1", "attack", "safe_zone", timestamp=1.0)
    assert a1.id == a2.id
    assert len(a1.id) == 16

def _test_norm_violation_content_addressing():
    from normsync.norm import NormViolation
    v1 = NormViolation("norm1", "name", "act1", "agent1", "desc1")
    v2 = NormViolation("norm1", "name", "act1", "agent2", "desc2")
    assert v1.id == v2.id  # id based on norm_id|action_id

def _test_norm_revision_serialization():
    from normsync.norm import NormRevision
    rev = NormRevision("norm1", "repeal", reason="no longer needed", timestamp=1.0)
    d = rev.to_dict()
    assert d["norm_id"] == "norm1"
    assert d["revision_type"] == "repeal"
    assert d["reason"] == "no longer needed"

run("WorldNorm content-addressing: same inputs → same id", _test_world_norm_content_addressing)
run("WorldNorm: different inputs → different id", _test_world_norm_different_inputs_different_id)
run("AgentAction content-addressing", _test_agent_action_content_addressing)
run("NormViolation content-addressing (norm_id|action_id)", _test_norm_violation_content_addressing)
run("NormRevision serializes correctly", _test_norm_revision_serialization)


# ── 3. NormMonitor operations ─────────────────────────────────────────────────

section("3. NormMonitor operations")

def _test_monitor_detects_violation():
    from normsync.monitor import NormMonitor
    from normsync.norm import AgentAction, WorldNorm
    monitor = NormMonitor()
    monitor.add_norm(WorldNorm("no-attack", "desc", "safe_zone", "attack"))
    action = AgentAction("agent1", "attack", "safe_zone")
    violations = monitor.check(action)
    assert len(violations) == 1
    assert violations[0].norm_name == "no-attack"

def _test_monitor_allows_permitted_action():
    from normsync.monitor import NormMonitor
    from normsync.norm import AgentAction, WorldNorm
    monitor = NormMonitor()
    monitor.add_norm(WorldNorm("no-attack", "desc", "safe_zone", "attack"))
    action = AgentAction("agent1", "trade", "safe_zone")
    violations = monitor.check(action)
    assert violations == [], f"Expected no violations for 'trade', got: {violations}"

def _test_monitor_repeal_stops_violations():
    from normsync.monitor import NormMonitor
    from normsync.norm import AgentAction, WorldNorm
    monitor = NormMonitor()
    norm = WorldNorm("no-attack", "desc", "safe_zone", "attack")
    monitor.add_norm(norm)
    rev = monitor.repeal_norm(norm.id)
    assert rev is not None
    assert rev.revision_type == "repeal"
    action = AgentAction("agent1", "attack", "safe_zone")
    violations = monitor.check(action)
    assert violations == [], "Repealed norm should not trigger violations"

run("NormMonitor detects attack-in-safe-zone violation", _test_monitor_detects_violation)
run("NormMonitor: trade is allowed (no violation)", _test_monitor_allows_permitted_action)
run("Repeal norm → no more violations", _test_monitor_repeal_stops_violations)


# ── 4. Report formatters ──────────────────────────────────────────────────────

section("4. Report formatters")

def _test_to_json_valid():
    import json
    from normsync.norm import WorldNorm
    from normsync.report import to_json
    norms = [WorldNorm("no-attack", "desc", "safe_zone", "attack")]
    result = to_json(norms)
    data = json.loads(result)
    assert "norms" in data
    assert "norm_count" in data
    assert data["norm_count"] == 1

def _test_to_markdown_has_table():
    from normsync.norm import WorldNorm
    from normsync.report import to_markdown
    norms = [WorldNorm("no-attack", "desc", "safe_zone", "attack")]
    result = to_markdown(norms)
    assert "|" in result, "Markdown output should have table characters"
    assert "no-attack" in result

def _test_print_violations_outputs():
    import io
    from rich.console import Console
    from normsync.norm import NormViolation
    from normsync.report import print_violations
    violations = [NormViolation("n1", "no-attack", "a1", "agent1", "Violated")]
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    print_violations(violations, console=con)
    output = buf.getvalue()
    assert len(output) > 0, "print_violations should produce output"
    assert "agent1" in output

run("to_json() returns valid JSON with expected keys", _test_to_json_valid)
run("to_markdown() returns markdown with table chars", _test_to_markdown_has_table)
run("print_violations() outputs Rich table with agent_id", _test_print_violations_outputs)


# ── 5. CLI ────────────────────────────────────────────────────────────────────

section("5. CLI (normsync)")

def _test_cli_help():
    r = subprocess.run(
        [PYTHON, "-m", "normsync.cli", "--help"],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20, "Help output is empty"

def _test_cli_add():
    r = subprocess.run(
        [PYTHON, "-m", "normsync.cli", "add",
         "test-norm", "desc", "safe_zone", "attack",
         "--db", str(tempfile.mktemp(suffix=".db"))],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "test-norm" in r.stdout

def _test_cli_status_no_db():
    r = subprocess.run(
        [PYTHON, "-m", "normsync.cli", "status",
         "--db", "/tmp/nonexistent_normsync_smoke.db"],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "No database" in r.stdout

def _test_cli_violations_help():
    r = subprocess.run(
        [PYTHON, "-m", "normsync.cli", "violations", "--help"],
        capture_output=True, text=True
    )
    assert r.returncode == 0

run("normsync --help returns 0", _test_cli_help)
run("normsync add creates norm successfully", _test_cli_add)
run("normsync status with no db returns gracefully", _test_cli_status_no_db)
run("normsync violations --help returns 0", _test_cli_violations_help)


# ── 6. FastAPI server ─────────────────────────────────────────────────────────

section("6. FastAPI server (normsync[api])")

def _test_api_import():
    from normsync.api import app
    assert app.title == "normsync API"

def _test_api_health():
    from fastapi.testclient import TestClient
    from normsync.api import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()

def _test_api_post_norm():
    from fastapi.testclient import TestClient
    import importlib
    import normsync.api as api_module
    importlib.reload(api_module)
    from normsync.api import app
    client = TestClient(app)
    r = client.post("/norm", json={
        "name": "no-attack",
        "description": "No attacking",
        "condition": "safe_zone",
        "prohibited": "attack",
    })
    assert r.status_code == 200
    assert "id" in r.json()

def _test_api_check_violation():
    from fastapi.testclient import TestClient
    import importlib
    import normsync.api as api_module
    importlib.reload(api_module)
    from normsync.api import app
    client = TestClient(app)
    client.post("/norm", json={
        "name": "no-attack",
        "description": "No attacking",
        "condition": "safe_zone",
        "prohibited": "attack",
    })
    r = client.post("/check", json={
        "agent_id": "agent1",
        "action": "attack",
        "location": "safe_zone",
    })
    assert r.status_code == 200
    assert r.json()["has_violations"] is True

run("normsync.api imports and app.title is correct", _test_api_import)
run("GET /health returns {status: ok, version: ...}", _test_api_health)
run("POST /norm adds norm and returns id", _test_api_post_norm)
run("POST /check detects violation in safe_zone", _test_api_check_violation)


# ── 7. MCP server ─────────────────────────────────────────────────────────────

section("7. MCP server (normsync[mcp])")

def _test_mcp_server_importable():
    import normsync.mcp_server as m
    assert hasattr(m, "run_server")

def _test_mcp_server_loads_cleanly():
    import normsync.mcp_server  # noqa: F401

def _test_mcp_server_has_tools():
    import ast
    import normsync.mcp_server as m
    src = open(m.__file__).read()
    assert "add_norm" in src
    assert "check_action" in src
    assert "list_violations" in src

run("mcp_server.py imports without error", _test_mcp_server_importable)
run("mcp_server module loads cleanly (no import-time crash)", _test_mcp_server_loads_cleanly)
run("mcp_server defines add_norm, check_action, list_violations tools", _test_mcp_server_has_tools)


# ── 8. Agent config files ─────────────────────────────────────────────────────

section("8. Agent config files (what a clone gives you)")

def _check_file_nonempty(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    assert p.stat().st_size > 50, f"File too small (likely empty): {rel}"

def _check_json_valid(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    json.loads(p.read_text())

def _check_yaml_parseable(rel: str) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
        p = REPO_ROOT / rel
        assert p.exists(), f"Missing: {rel}"
        yaml.safe_load(p.read_text())
    except ImportError:
        content = (REPO_ROOT / rel).read_text()
        assert len(content) > 20, f"File appears empty: {rel}"

def _test_claude_commands():
    commands = list((REPO_ROOT / ".claude/commands").glob("*.md"))
    assert len(commands) >= 4, f"Expected ≥4 slash commands, found {len(commands)}"

def _test_openai_tools_valid():
    _check_json_valid("tools/openai-tools.json")
    tools = json.loads((REPO_ROOT / "tools/openai-tools.json").read_text())
    assert len(tools) >= 3
    assert all("function" in t for t in tools)

def _test_openapi_yaml_parseable():
    _check_yaml_parseable("openapi.yaml")

run("AGENTS.md exists and non-empty", lambda: _check_file_nonempty("AGENTS.md"))
run("CLAUDE.md exists and non-empty", lambda: _check_file_nonempty("CLAUDE.md"))
run("CODEX.md exists and non-empty", lambda: _check_file_nonempty("CODEX.md"))
run(".github/copilot-instructions.md exists", lambda: _check_file_nonempty(".github/copilot-instructions.md"))
def _test_cursor_rules():
    mdc_files = list((REPO_ROOT / ".cursor/rules").glob("*.mdc"))
    assert len(mdc_files) >= 1, f"Expected ≥1 .mdc file in .cursor/rules/, found none"

run(".cursor/rules/ has at least one .mdc file", _test_cursor_rules)
run(".windsurfrules exists", lambda: _check_file_nonempty(".windsurfrules"))
run(".aider.conf.yml exists", lambda: _check_file_nonempty(".aider.conf.yml"))
run(".continue/config.json is valid JSON", lambda: _check_json_valid(".continue/config.json"))
run(".claude/commands/ has ≥4 slash commands", _test_claude_commands)
run("tools/openai-tools.json is valid JSON with ≥3 tools", _test_openai_tools_valid)
run("openapi.yaml is parseable YAML", _test_openapi_yaml_parseable)


# ── 9. Docs site ──────────────────────────────────────────────────────────────

section("9. MkDocs documentation site")

def _test_mkdocs_yml():
    _check_file_nonempty("mkdocs.yml")
    content = (REPO_ROOT / "mkdocs.yml").read_text()
    assert "site_name" in content
    assert "material" in content

def _test_docs_pages():
    docs = list((REPO_ROOT / "docs").glob("*.md"))
    assert len(docs) >= 8, f"Expected ≥8 doc pages, found {len(docs)}"
    names = {p.name for p in docs}
    for required in ("index.md", "quickstart.md", "architecture.md", "api-reference.md"):
        assert required in names, f"Missing docs/{required}"

run("mkdocs.yml exists with site_name and material theme", _test_mkdocs_yml)
run("docs/ has ≥8 pages including index, quickstart, architecture, api-reference", _test_docs_pages)


# ── 10. examples/demo.py ─────────────────────────────────────────────────────

section("10. examples/demo.py end-to-end")

def _test_demo_runs():
    demo = REPO_ROOT / "examples" / "demo.py"
    assert demo.exists(), "examples/demo.py not found"
    r = subprocess.run(
        [PYTHON, str(demo)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT)
    )
    if r.returncode != 0:
        raise AssertionError(f"demo.py exited {r.returncode}:\n{r.stderr[-500:]}")

run("examples/demo.py runs end-to-end without error", _test_demo_runs)


# ── Summary ───────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n{'═'*60}")
print(f"{BOLD}Results: {len(passed)}/{total} passed{RESET}")

if failed:
    print(f"{RED}Failed ({len(failed)}):{RESET}")
    for name, reason in failed:
        print(f"  {RED}✗{RESET} {name}")
        short = reason.split("\n")[0][:120]
        print(f"    {YELLOW}→ {short}{RESET}")
    print(f"\n{YELLOW}Tip: run with --verbose for full tracebacks{RESET}")
else:
    print(f"{GREEN}All {total} checks passed — normsync is ready to ship{RESET}")

print(f"{'═'*60}\n")
sys.exit(0 if not failed else 1)
