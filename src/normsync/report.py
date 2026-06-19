"""Report formatters for normsync."""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from normsync.norm import NormViolation, WorldNorm


def print_violations(
    violations: list[NormViolation], console: Console | None = None
) -> None:
    """Print violations as a Rich table."""
    con = console or Console()
    if not violations:
        con.print("[green]No violations found.[/green]")
        return
    table = Table(title="Norm Violations", show_header=True, header_style="bold red")
    table.add_column("ID", style="dim")
    table.add_column("Agent")
    table.add_column("Norm")
    table.add_column("Description")
    table.add_column("Severity")
    for v in violations:
        table.add_row(v.id[:8], v.agent_id, v.norm_name, v.description[:60], v.severity)
    con.print(table)


def to_json(
    norms: list[WorldNorm],
    violations: list[NormViolation] | None = None,
) -> str:
    """Serialize norms and optionally violations to JSON."""
    data: dict[str, Any] = {
        "norms": [n.to_dict() for n in norms],
        "norm_count": len(norms),
        "active_count": sum(1 for n in norms if n.active),
    }
    if violations is not None:
        data["violations"] = [v.to_dict() for v in violations]
        data["violation_count"] = len(violations)
        data["has_violations"] = len(violations) > 0
    return json.dumps(data, indent=2)


def to_markdown(
    norms: list[WorldNorm],
    violations: list[NormViolation] | None = None,
) -> str:
    """Render norms and violations as Markdown."""
    lines = [
        "# normsync Report\n",
        f"**Active norms:** {sum(1 for n in norms if n.active)}\n",
    ]
    if norms:
        lines += [
            "## Norms\n",
            "| Name | Scope | Condition | Prohibited | Active |",
            "|------|-------|-----------|-----------|--------|",
        ]
        for n in norms:
            lines.append(
                f"| {n.name} | {n.scope} | {n.condition} | {n.prohibited} | {n.active} |"
            )
        lines.append("")
    if violations:
        lines += [
            "## Violations\n",
            "| Agent | Norm | Description | Severity |",
            "|-------|------|-------------|----------|",
        ]
        for v in violations:
            lines.append(
                f"| {v.agent_id} | {v.norm_name} | {v.description} | {v.severity} |"
            )
    return "\n".join(lines)
