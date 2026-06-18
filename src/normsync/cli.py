"""Click CLI for normsync."""
from __future__ import annotations

import os
import time

import click
from rich.console import Console
from rich.table import Table

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm
from normsync.report import print_violations, to_json, to_markdown
from normsync.store import NormStore

DEFAULT_DB = ".normsync/norms.db"
console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """normsync — World constitution engine for norm-governed agents."""


@main.command("add")
@click.argument("name")
@click.argument("description")
@click.argument("condition")
@click.argument("prohibited")
@click.option("--db", default=DEFAULT_DB, help="Path to SQLite database")
@click.option("--scope", default="global", help="Norm scope")
@click.option("--priority", default=0, type=int, help="Norm priority")
def add_norm(
    name: str,
    description: str,
    condition: str,
    prohibited: str,
    db: str,
    scope: str,
    priority: int,
) -> None:
    """Add a new norm to the constitution."""
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    store = NormStore(db)
    norm = WorldNorm(
        name=name,
        description=description,
        condition=condition,
        prohibited=prohibited,
        scope=scope,
        priority=priority,
    )
    monitor = NormMonitor(store.get_norms())
    monitor.add_norm(norm)
    store.save_norm(norm)
    console.print(f"[green]Added norm:[/green] {norm.name} (id={norm.id})")
    store.close()


@main.command("check")
@click.argument("agent_id")
@click.argument("action")
@click.argument("location", default="")
@click.option("--db", default=DEFAULT_DB, help="Path to SQLite database")
@click.option("--target", default="", help="Target of action")
@click.option("--faction", default="", help="Agent faction")
def check_action(
    agent_id: str,
    action: str,
    location: str,
    db: str,
    target: str,
    faction: str,
) -> None:
    """Check an action against active norms."""
    if not os.path.exists(db):
        console.print("[yellow]No database found. No norms to check against.[/yellow]")
        return
    store = NormStore(db)
    norms = store.get_norms(active_only=True)
    monitor = NormMonitor(norms)
    act = AgentAction(
        agent_id=agent_id,
        action=action,
        location=location,
        target=target,
        faction=faction,
        timestamp=time.time(),
    )
    violations = monitor.check(act)
    for v in violations:
        store.save_violation(v)
    if violations:
        console.print(f"[red]Found {len(violations)} violation(s)![/red]")
        print_violations(violations, console)
    else:
        console.print("[green]No violations detected.[/green]")
    store.close()


@main.command("violations")
@click.option("--db", default=DEFAULT_DB, help="Path to SQLite database")
@click.option(
    "--format",
    "fmt",
    default="table",
    type=click.Choice(["table", "json", "markdown"]),
)
def list_violations(db: str, fmt: str) -> None:
    """List all recorded violations."""
    if not os.path.exists(db):
        console.print("[yellow]No database found.[/yellow]")
        return
    store = NormStore(db)
    violations = store.get_violations()
    if fmt == "json":
        norms = store.get_norms()
        click.echo(to_json(norms, violations))
    elif fmt == "markdown":
        norms = store.get_norms()
        click.echo(to_markdown(norms, violations))
    else:
        print_violations(violations, console)
    store.close()


@main.command("revisions")
@click.option("--db", default=DEFAULT_DB, help="Path to SQLite database")
def list_revisions(db: str) -> None:
    """List norm revisions."""
    if not os.path.exists(db):
        console.print("[yellow]No database found.[/yellow]")
        return
    store = NormStore(db)
    revisions = store.get_revisions()
    if not revisions:
        console.print("[yellow]No revisions found.[/yellow]")
        store.close()
        return
    table = Table(title="Norm Revisions")
    table.add_column("ID", style="dim")
    table.add_column("Norm ID")
    table.add_column("Type")
    table.add_column("Reason")
    for r in revisions:
        table.add_row(r.id[:8], r.norm_id[:8], r.revision_type, r.reason)
    console.print(table)
    store.close()


@main.command("status")
@click.option("--db", default=DEFAULT_DB, help="Path to SQLite database")
def status(db: str) -> None:
    """Show normsync status."""
    if not os.path.exists(db):
        console.print(
            "[yellow]No database found. Run 'normsync add' to create one.[/yellow]"
        )
        return
    store = NormStore(db)
    norms = store.get_norms()
    violations = store.get_violations()
    revisions = store.get_revisions()
    active = [n for n in norms if n.active]
    console.print("[bold]normsync status[/bold]")
    console.print(f"  Norms: {len(norms)} total, {len(active)} active")
    console.print(f"  Violations: {len(violations)}")
    console.print(f"  Revisions: {len(revisions)}")


if __name__ == "__main__":
    main()
