"""Standalone demo of the normsync library.

Run: python examples/demo.py
"""
from __future__ import annotations

from rich.console import Console

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm
from normsync.report import print_violations, to_json
from normsync.store import NormStore

console = Console()


def main() -> None:
    console.print("[bold cyan]normsync demo — World Constitution Engine[/bold cyan]\n")

    # 1. Create norms
    norm_safe = WorldNorm(
        name="no-attack-in-safe-zone",
        description="Attacking is prohibited in safe zones",
        condition="safe_zone",
        prohibited="attack",
        scope="global",
        priority=10,
    )
    norm_market = WorldNorm(
        name="no-steal-in-market",
        description="Stealing is prohibited in market zones",
        condition="market",
        prohibited="steal",
        scope="global",
        priority=5,
    )

    # 2. Create store and monitor
    store = NormStore(":memory:")
    monitor = NormMonitor()
    monitor.add_norm(norm_safe)
    monitor.add_norm(norm_market)
    store.save_norm(norm_safe)
    store.save_norm(norm_market)
    console.print(f"[green]Loaded {len(monitor.active_norms())} active norms[/green]")

    # 3. Check 3 actions (2 violations, 1 allowed)
    console.print("\n[bold]Checking agent actions...[/bold]")

    actions = [
        AgentAction("hero", "attack", "safe_zone", timestamp=1.0),
        AgentAction("villain", "steal", "market", timestamp=2.0),
        AgentAction("merchant", "trade", "market", timestamp=3.0),
    ]

    all_violations = []
    for action in actions:
        violations = monitor.check(action)
        if violations:
            console.print(
                f"  [red]VIOLATION[/red]: {action.agent_id} -> {action.action} in {action.location}"
            )
            for v in violations:
                store.save_violation(v)
            all_violations.extend(violations)
        else:
            console.print(
                f"  [green]OK[/green]: {action.agent_id} -> {action.action} in {action.location}"
            )

    # 4. Print violations table
    console.print("\n[bold]Violation Report:[/bold]")
    print_violations(all_violations, console=console)

    # 5. Repeal norm and recheck
    console.print("\n[bold]Repealing 'no-attack-in-safe-zone' norm...[/bold]")
    rev = monitor.repeal_norm(norm_safe.id)
    if rev:
        store.save_revision(rev)
        console.print(f"[yellow]Norm repealed. Revision id: {rev.id}[/yellow]")

    attack_again = AgentAction("hero", "attack", "safe_zone", timestamp=4.0)
    violations_after = monitor.check(attack_again)
    if violations_after:
        console.print("[red]Still violations after repeal![/red]")
    else:
        console.print(
            "[green]No violations after repeal — norm successfully deactivated[/green]"
        )

    # 6. Print JSON report
    console.print("\n[bold]JSON Report:[/bold]")
    report = to_json(store.get_norms(), store.get_violations())
    console.print(report)

    store.close()
    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    main()
